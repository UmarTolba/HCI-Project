package src.com.nmmu.ticketa;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

public class CameraManager {

    public enum Mode { NONE, TUIO, GESTURE }

    public static CameraManager instance;

    private static final String PYTHON = System.getProperty("kiosk.python", "python");
    private static final String GESTURE_CAMERA = System.getProperty("kiosk.gestureCamera", "0");
    private static final boolean USE_CAMERA_BRIDGE = Boolean.getBoolean("kiosk.useCameraBridge");

    private final Object lock = new Object();
    private final ExecutorService worker = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "camera-manager");
        t.setDaemon(true);
        return t;
    });
    private final List<Process> running = new ArrayList<>();
    private final Set<Process> stoppedByUs = new HashSet<>();   
    private volatile Consumer<String> problemListener;
    private volatile String lastProblem;
    private Mode mode = Mode.NONE;
    private String screen = "START";
    private boolean scanHold = false;

    public void setProblemListener(Consumer<String> listener) {
        problemListener = listener;
        String pending = lastProblem;
        if (pending != null && listener != null) {
            listener.accept(pending);                        
        }
    }

    private void report(String message) {
        System.out.println("[CAMERA] PROBLEM: " + message);
        lastProblem = message;
        Consumer<String> listener = problemListener;
        if (listener != null) {
            listener.accept(message);
        }
    }


    public void onScreen(String name) {
        synchronized (lock) {
            screen = name;
        }
        refresh();
    }

    public void setScanHold(boolean hold) {
        synchronized (lock) {
            scanHold = hold;
        }
        refresh();
    }

    private void refresh() {
        final Mode wanted;
        synchronized (lock) {
            wanted = scanHold ? Mode.TUIO : modeFor(screen);
        }
        try {
            worker.submit(() -> switchTo(wanted));
        } catch (RejectedExecutionException e) {
        }
    }

    private static Mode modeFor(String screen) {
        return Mode.GESTURE;                               
    }

    public void stopAll() {
        worker.shutdownNow();
        synchronized (lock) {
            stopProcesses();
            mode = Mode.NONE;
        }
    }


    private void switchTo(Mode wanted) {
        synchronized (lock) {
            if (wanted == mode) {
                return;
            }
            boolean hadCamera = mode != Mode.NONE;
            lastProblem = null;
            stopProcesses();
            mode = Mode.NONE;
            if (hadCamera && wanted != Mode.NONE) {
                pause(700);                                 
            }
            try {
                if (wanted == Mode.TUIO) {
                    startTuio();
                } else if (wanted == Mode.GESTURE) {
                    startGestures();
                }
                mode = wanted;
                System.out.println("[CAMERA] mode: " + wanted);
            } catch (IOException e) {
                report("could not start the " + wanted + " camera: " + e.getMessage()
                        + " (is Python installed? use -Dkiosk.python=py or the full path to python.exe)");
                stopProcesses();
            }
        }
    }

    private void startTuio() throws IOException {
        File tools = findDir(new String[] {"../tools/reacTIVision", "tools/reacTIVision"}, "reacTIVision.exe");
        File bridge = findDir(new String[] {"../bridge", "bridge"}, "bridge.py");
        if (tools == null) {
            System.out.println("[CAMERA] reacTIVision not found in tools/reacTIVision");
        } else if (USE_CAMERA_BRIDGE) {
            launch("camera_bridge.py", tools, PYTHON, "camera_bridge.py");
        } else {
            launch("reacTIVision", tools, new File(tools, "reacTIVision.exe").getPath());
        }
        if (bridge == null) {
            System.out.println("[CAMERA] bridge/bridge.py not found, markers will not reach the kiosk");
        } else {
            launch("the marker bridge", bridge, PYTHON, "bridge.py", "--no-gestures", "--no-console",
        "--java-port", "5055");
        }
    }

    private void startGestures() throws IOException {
        File bridge = findDir(new String[] {"../bridge", "bridge"}, "bridge.py");
        if (bridge == null) {
            throw new IOException("bridge/bridge.py not found");
        }
        launch("the gesture program", bridge, PYTHON, "bridge.py", "--no-tuio", "--no-console",
        "--camera", GESTURE_CAMERA, "--java-port", "5055");
    }

    private void launch(String label, File dir, String... command) throws IOException {
        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(dir);
        builder.inheritIO();                                // Python / reacTIVision messages appear in this console
        final Process process = builder.start();
        running.add(process);
        System.out.println("[CAMERA] started " + label + " in " + dir);
        process.onExit().thenAccept(done -> {
            boolean ours;
            synchronized (lock) {
                ours = stoppedByUs.contains(process);
            }
            if (!ours && done.exitValue() != 0) {            // crashed or Python is missing, not a normal stop
                report(label + " stopped (exit code " + done.exitValue() + "). Read the messages above in the console.");
            }
        });
    }

    private void stopProcesses() {
        stoppedByUs.addAll(running);
        for (Process p : running) {
            p.descendants().forEach(ProcessHandle::destroy);   // e.g. reacTIVision started by camera_bridge.py
            p.destroy();
        }
        for (Process p : running) {
            try {
                if (!p.waitFor(2, TimeUnit.SECONDS)) {
                    p.destroyForcibly();
                }
            } catch (InterruptedException e) {
                p.destroyForcibly();
                Thread.currentThread().interrupt();
            }
        }
        running.clear();
    }

    private static File findDir(String[] candidates, String marker) {
        for (String path : candidates) {
            File dir = new File(path).getAbsoluteFile();      // absolute, because the child process changes directory
            if (new File(dir, marker).exists()) {
                return dir;
            }
        }
        return null;
    }

    private static void pause(int millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
