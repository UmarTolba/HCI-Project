package src.com.nmmu.ticketa;
import java.awt.BorderLayout;
import java.awt.CardLayout;
import java.awt.Color;
import java.awt.Component;
import java.awt.Font;
import java.awt.KeyboardFocusManager;
import java.awt.event.KeyEvent;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.SwingConstants;
import javax.swing.Timer;

public class MainFrame extends JFrame {

    CardLayout cards = new CardLayout();
    JPanel root = new JPanel(cards);

    JLabel startLabel = makeLabel(40);
    JLabel ticketTypeLabel = makeLabel(30);
    JPanel startPanel = new JPanel(new BorderLayout(20, 20));
    JPanel orderButtons = new JPanel();
    JButton gestureOrderButton = new JButton("Order with gestures");
    JButton manualOrderButton = new JButton("Order manually");
    JPanel manualPanel = new JPanel();
    Process gestureProcess;
    JLabel dateLabel = makeLabel(30);
    JLabel timeLabel = makeLabel(30);
    JLabel summaryLabel = makeLabel(30);
    JLabel errorLabel = makeLabel(34);

    String screen = "START";
    String screenBeforeError = "START";
    Ticket ticket;
    int ticketTypeIndex = 0;
    int dateIndex = 0;
    int slotIndex = 0;
    Timer timer;

    public MainFrame() {
        setTitle("Museum Ticket Kiosk");
        setSize(1200, 700);
        setLocationRelativeTo(null);
        setDefaultCloseOperation(EXIT_ON_CLOSE);

        startLabel.setText("<html><center>Welcome to the Museum Ticket Kiosk<br><br>"
                + "Choose how you would like to order<br>"
                + "You can also show your ticket marker to the camera</center></html>");
        styleOrderButton(gestureOrderButton);
        styleOrderButton(manualOrderButton);
        gestureOrderButton.addActionListener(e -> startGestureOrdering());
        manualOrderButton.addActionListener(e -> showManualTicketTypes());
        orderButtons.add(manualOrderButton);
        orderButtons.add(gestureOrderButton);
        startPanel.add(startLabel, BorderLayout.CENTER);
        startPanel.add(orderButtons, BorderLayout.SOUTH);
        manualPanel.setLayout(new javax.swing.BoxLayout(manualPanel, javax.swing.BoxLayout.Y_AXIS));

        errorLabel.setForeground(new Color(160, 0, 0));

        root.add(startPanel, "START");
        root.add(ticketTypeLabel, "GESTURE_SELECT");
        root.add(manualPanel, "MANUAL");
        root.add(dateLabel, "DATE");
        root.add(timeLabel, "TIME");
        root.add(summaryLabel, "SUMMARY");
        root.add(errorLabel, "ERROR");
        setContentPane(root);

        KeyboardFocusManager.getCurrentKeyboardFocusManager().addKeyEventDispatcher(e -> {
            if (e.getID() == KeyEvent.KEY_PRESSED) {
                handleKey(e.getKeyCode());
            }
            return false;
        });

        goToStart();
    }

    JLabel makeLabel(int size) {
        JLabel label = new JLabel("", SwingConstants.CENTER);
        label.setFont(new Font("SansSerif", Font.BOLD, size));
        return label;
    }

    void styleOrderButton(JButton button) {
        button.setFont(new Font("SansSerif", Font.BOLD, 26));
    }

    void handleKey(int key) {
        if (key == KeyEvent.VK_1) handle("marker", "1");
        if (key == KeyEvent.VK_2) handle("marker", "2");
        if (key == KeyEvent.VK_3) handle("marker", "3");
        if (key == KeyEvent.VK_4) handle("marker", "4");
        if (key == KeyEvent.VK_LEFT) handle("gesture", "swipe_left");
        if (key == KeyEvent.VK_RIGHT) handle("gesture", "swipe_right");
        if (key == KeyEvent.VK_ENTER) handle("gesture", "raise_hand");
        if (key == KeyEvent.VK_ESCAPE) handle("gesture", "cross_arms");
        if (key == KeyEvent.VK_X) handle("gesture", "unknown");
    }

    public void handle(String type, String value) {
        if (screen.equals("ERROR")) {
            return;
        }
        if (type.equals("marker")) {
            onMarker(value);
        } else if (type.equals("gesture")) {
            onGesture(value);
        }
    }

    void onMarker(String value) {
        if (screen.equals("SUMMARY") || screen.equals("GESTURE_SELECT")) {
            return;
        }
        int id = 0;
        try {
            id = Integer.parseInt(value);
        } catch (Exception e) {
            showError("Unknown marker. Please try again.");
            return;
        }
        Ticket found = ContentProvider.getTicket(id);
        if (found == null) {
            showError("Unknown marker. Please try again.");
            return;
        }
        ticket = found;
        dateIndex = 0;
        slotIndex = 0;
        showManualDate();
    }

    void onGesture(String gesture) {
        if (!screen.equals("GESTURE_SELECT") && !screen.equals("DATE") && !screen.equals("TIME")) {
            return;
        }
        if (screen.equals("GESTURE_SELECT") && gesture.equals("raise_hand")) {
            selectTicketType();
        } else if (gesture.equals("swipe_right")) {
            move(1);
        } else if (gesture.equals("swipe_left")) {
            move(-1);
        } else if (gesture.equals("raise_hand")) {
            confirm();
        } else if (gesture.equals("cross_arms")) {
            goToStart();
        } else {
            showError("Gesture not recognized. Please try again.");
        }
    }

    void move(int step) {
        if (screen.equals("GESTURE_SELECT")) {
            int count = 5;
            ticketTypeIndex = (ticketTypeIndex + step + count) % count;
            showGestureMenu();
        } else if (screen.equals("DATE")) {
            dateIndex = (dateIndex + step + 3) % 3;
            showDateScreen();
        } else if (screen.equals("TIME")) {
            int count = ContentProvider.times.length;
            slotIndex = (slotIndex + step + count) % count;
            showTimeScreen();
        }
    }

    void confirm() {
        if (screen.equals("DATE")) {
            slotIndex = 0;
            showTimeScreen();
        } else if (screen.equals("TIME")) {
            if (ContentProvider.seats[slotIndex] == 0) {
                showError("This time slot is full. Choose another slot.");
            } else {
                showSummaryScreen();
            }
        }
    }

    void selectTicketType() {
        ticket = ContentProvider.getTicket(ticketTypeIndex + 1);
        dateIndex = 0;
        slotIndex = 0;
        showDateScreen();
    }

    void goToStart() {
        stopTimer();
        stopGestureRecognizer();
        ticket = null;
        ticketTypeIndex = 0;
        show("START");
    }

    void startGestureOrdering() {
        try {
            File projectRoot = findProjectRoot();
            File script = new File(projectRoot, "live_gestures.py");
            ProcessBuilder builder = new ProcessBuilder(
                    findPython(projectRoot), script.getAbsolutePath(),
                    "--camera", "0", "--host", "127.0.0.1", "--port", "5000");
            builder.directory(projectRoot);
            builder.redirectErrorStream(true);
            gestureProcess = builder.start();
            Process process = gestureProcess;
            showGestureMenu();
            Thread outputThread = new Thread(() -> watchGestureProcess(process),
                    "gesture-recognizer-output");
            outputThread.setDaemon(true);
            outputThread.start();
        } catch (IOException e) {
            showError("Could not start live_gestures.py: " + escapeHtml(e.getMessage()));
        }
    }

    File findProjectRoot() throws IOException {
        File directory = new File(".").getCanonicalFile();
        for (int i = 0; i < 4 && directory != null; i++, directory = directory.getParentFile()) {
            if (new File(directory, "live_gestures.py").isFile()
                    && new File(directory, "gesture_templates.pkl").isFile()) {
                return directory;
            }
        }
        throw new IOException("Could not find live_gestures.py and gesture_templates.pkl from "
                + new File(".").getCanonicalPath());
    }

    String findPython(File projectRoot) {
        String executable = System.getProperty("os.name").toLowerCase().contains("win")
                ? "python.exe" : "python";
        String[] candidates = {
            new File(projectRoot, ".venv312/bin/python").getPath(),
            new File(projectRoot, ".venv312/Scripts/python.exe").getPath(),
            new File(projectRoot, ".venv/bin/python").getPath(),
            new File(projectRoot, ".venv/Scripts/python.exe").getPath()
        };
        for (String candidate : candidates) {
            File file = new File(candidate);
            if (file.isFile() && file.canExecute()) {
                return file.getAbsolutePath();
            }
        }
        return executable;
    }

    void watchGestureProcess(Process process) {
        List<String> output = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("[GESTURE] " + line);
                synchronized (output) {
                    if (output.size() == 12) {
                        output.remove(0);
                    }
                    output.add(line);
                }
            }
            int exitCode = process.waitFor();
            if (gestureProcess == process) {
                String detail;
                synchronized (output) {
                    detail = output.isEmpty() ? "" : ": " + escapeHtml(output.get(output.size() - 1));
                }
                javax.swing.SwingUtilities.invokeLater(() -> {
                    if (gestureProcess == process && screen.equals("GESTURE_SELECT")) {
                        gestureProcess = null;
                        showError("Gesture recognizer stopped (exit " + exitCode + ")" + detail);
                    }
                });
            }
        } catch (IOException e) {
            System.err.println("Could not read gesture recognizer output: " + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    void stopGestureRecognizer() {
        Process process = gestureProcess;
        gestureProcess = null;
        if (process != null) {
            process.destroy();
        }
    }

    String escapeHtml(String text) {
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }

    void showGestureMenu() {
        String text = "<html><center>Order with gestures<br><br>Choose your ticket type<br><br>";
        for (int i = 0; i < 5; i++) {
            Ticket option = ContentProvider.getTicket(i + 1);
            if (i == ticketTypeIndex) {
                text += "<font color='blue'>&gt; " + option.name + " - " + option.price + " &lt;</font><br>";
            } else {
                text += option.name + " - " + option.price + "<br>";
            }
        }
        text += "<br>Swipe left or right to choose<br>"
                + "Raise your hand to select<br>"
                + "Cross your arms to return to the start screen</center></html>";
        ticketTypeLabel.setText(text);
        show("GESTURE_SELECT");
    }

    void showManualTicketTypes() {
        manualPanel.removeAll();
        manualPanel.add(makeLabel(30));
        ((JLabel) manualPanel.getComponent(0)).setText("Choose a ticket type");
        for (int i = 1; i <= 5; i++) {
            int ticketId = i;
            Ticket option = ContentProvider.getTicket(i);
            addManualButton(option.name + " - " + option.price, () -> {
                ticket = ContentProvider.getTicket(ticketId);
                dateIndex = 0;
                slotIndex = 0;
                showManualDate();
            });
        }
        addManualButton("Back", this::goToStart);
        showManualPanel();
    }

    void showManualDate() {
        manualPanel.removeAll();
        JLabel heading = makeLabel(26);
        heading.setText("<html><center>" + ticket.name + " ticket - choose a date</center></html>");
        manualPanel.add(heading);
        for (int i = 0; i < 3; i++) {
            int index = i;
            String marker = i == dateIndex ? "  (selected)" : "";
            addManualButton(dateText(i) + marker, () -> {
                dateIndex = index;
                showManualDate();
            });
        }
        addManualButton("Continue", this::showManualTimes);
        addManualButton("Back to ticket types", this::showManualTicketTypes);
        showManualPanel();
    }

    void showManualTimes() {
        manualPanel.removeAll();
        JLabel heading = makeLabel(26);
        heading.setText("<html><center>" + ticket.name + " ticket on " + dateText(dateIndex)
                + " - choose a time</center></html>");
        manualPanel.add(heading);
        for (int i = 0; i < ContentProvider.times.length; i++) {
            int index = i;
            String seatText = ContentProvider.seats[i] == 0 ? " (FULL)"
                    : " (" + ContentProvider.seats[i] + " seats left)";
            String selected = i == slotIndex ? "  (selected)" : "";
            JButton button = addManualButton(ContentProvider.times[i] + seatText + selected, () -> {
                slotIndex = index;
                showManualTimes();
            });
            button.setEnabled(ContentProvider.seats[i] > 0);
        }
        addManualButton("Confirm reservation", this::confirm);
        addManualButton("Back to dates", this::showManualDate);
        showManualPanel();
    }

    JButton addManualButton(String text, Runnable action) {
        JButton button = new JButton(text);
        button.setFont(new Font("SansSerif", Font.PLAIN, 22));
        button.setAlignmentX(Component.CENTER_ALIGNMENT);
        button.setMaximumSize(new java.awt.Dimension(850, 54));
        button.addActionListener(e -> action.run());
        manualPanel.add(button);
        return button;
    }

    void showManualPanel() {
        manualPanel.revalidate();
        manualPanel.repaint();
        show("MANUAL");
    }

    void show(String name) {
        screen = name;
        cards.show(root, name);
    }

    void stopTimer() {
        if (timer != null) {
            timer.stop();
        }
    }

    String dateText(int index) {
        return LocalDate.now().plusDays(index).toString();
    }

    void showDateScreen() {
        String text = "<html><center>" + ticket.name + " ticket<br>" + ticket.price + "<br>" + ticket.rules
                + "<br><br>Choose a date<br><br>";
        for (int i = 0; i < 3; i++) {
            if (i == dateIndex) {
                text += "<font color='blue'>&gt; " + dateText(i) + " &lt;</font><br>";
            } else {
                text += dateText(i) + "<br>";
            }
        }
        text += "<br><font size='5'>Swipe to change - Raise your hand to confirm</font></center></html>";
        dateLabel.setText(text);
        show("DATE");
    }

    void showTimeScreen() {
        String text = "<html><center>" + ticket.name + " ticket<br>" + dateText(dateIndex)
                + "<br><br>Choose a time slot<br><br>";
        for (int i = 0; i < ContentProvider.times.length; i++) {
            String line = ContentProvider.times[i] + " (" + ContentProvider.seats[i] + " seats left)";
            if (ContentProvider.seats[i] == 0) {
                line = ContentProvider.times[i] + " (FULL)";
            }
            if (i == slotIndex) {
                text += "<font color='blue'>&gt; " + line + " &lt;</font><br>";
            } else {
                text += line + "<br>";
            }
        }
        text += "<br><font size='5'>Swipe to change - Raise your hand to confirm</font></center></html>";
        timeLabel.setText(text);
        show("TIME");
    }

    void showSummaryScreen() {
        stopGestureRecognizer();
        String code = makeCode();
        String time = ContentProvider.times[slotIndex];
        String date = dateText(dateIndex);

        summaryLabel.setText("<html><center>Reservation confirmed<br><br>1 x " + ticket.name + " ticket<br>"
                + date + " at " + time + "<br><br>Ticket code: <font color='blue'>" + code + "</font></center></html>");

        saveTicket(code, date, time);
        if (ScanStation.instance != null) {
            ScanStation.instance.ticketPrinted(code, ticket.name);
        }
        show("SUMMARY");

        stopTimer();
        timer = new Timer(10000, e -> goToStart());
        timer.setRepeats(false);
        timer.start();
    }

    void showError(String message) {
        screenBeforeError = screen;
        errorLabel.setText("<html><center>" + message + "</center></html>");
        show("ERROR");

        stopTimer();
        timer = new Timer(2500, e -> show(screenBeforeError));
        timer.setRepeats(false);
        timer.start();
    }

    String makeCode() {
        String letters = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        Random random = new Random();
        String code = "";
        for (int i = 0; i < 6; i++) {
            code += letters.charAt(random.nextInt(letters.length()));
        }
        return code;
    }

    void saveTicket(String code, String date, String time) {
        try {
            FileWriter writer = new FileWriter("tickets.txt", true);
            writer.write(code + " | " + ticket.name + " | " + date + " | " + time + "\n");
            writer.close();
        } catch (Exception e) {
            System.out.println("Could not save ticket");
        }
    }
}
