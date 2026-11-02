package src.com.nmmu.ticketa;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.ServerSocket;
import java.net.Socket;

/**
 * Java socket server (Lab 2, mirrored): receives the merged marker + gesture stream
 * from the Python bridge. One line per message, formatted  type:value
 *   marker:2          gesture:swipe_left
 *
 * Every connected client gets its own thread (Lab 2 "Threads"), so a second sender,
 * or a restarted bridge, never blocks behind the first one.
 */
public class SocketServer {

    /** Called on a background thread: use SwingUtilities.invokeLater before touching the UI. */
    public interface MessageListener {
        void onMessage(String type, String value);
    }

    private final int port;
    private final MessageListener listener;
    private ServerSocket server;
    private volatile boolean running = true;

    public SocketServer(int port, MessageListener listener) {
        this.port = port;
        this.listener = listener;
    }

    public void start() {
        Thread acceptThread = new Thread(this::acceptLoop, "socket-accept");
        acceptThread.setDaemon(true);
        acceptThread.start();
    }

    public void stop() {
        running = false;
        try {
            if (server != null) {
                server.close();
            }
        } catch (IOException ignored) {
        }
    }

    private void acceptLoop() {
        try {
            server = new ServerSocket(port);
            System.out.println("Socket server waiting on port " + port + " ...");
            while (running) {
                Socket client = server.accept();
                System.out.println("Bridge connected: " + client.getRemoteSocketAddress());
                Thread t = new Thread(() -> readClient(client), "socket-client");
                t.setDaemon(true);
                t.start();
            }
        } catch (IOException e) {
            if (running) {
                System.out.println("Socket server stopped: " + e.getMessage());
            }
        }
    }

    private void readClient(Socket client) {
        try (Socket c = client;
             BufferedReader in = new BufferedReader(new InputStreamReader(c.getInputStream(), "UTF-8"))) {
            String line;
            while ((line = in.readLine()) != null) {
                handleLine(line);
            }
        } catch (IOException e) {
            // client closed the connection
        }
        System.out.println("Bridge disconnected");
    }

    private void handleLine(String line) {
        int colon = line.indexOf(':');
        if (colon <= 0) {
            if (!line.trim().isEmpty()) {
                System.out.println("Ignored malformed message: " + line);
            }
            return;
        }
        String type = line.substring(0, colon).trim().toLowerCase();
        String value = line.substring(colon + 1).trim();
        System.out.println("Received  " + type + " : " + value);
        listener.onMessage(type, value);
    }
}
