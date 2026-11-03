package src.com.nmmu.ticketa;
import java.awt.CardLayout;
import java.awt.Color;
import java.awt.Font;
import java.awt.KeyboardFocusManager;
import java.awt.event.KeyEvent;
import java.io.FileWriter;
import java.time.LocalDate;
import java.util.Random;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.SwingConstants;
import javax.swing.Timer;

public class MainFrame extends JFrame {

    CardLayout cards = new CardLayout();
    JPanel root = new JPanel(cards);

    JLabel startLabel = makeLabel(40);
    JLabel dateLabel = makeLabel(30);
    JLabel timeLabel = makeLabel(30);
    JLabel summaryLabel = makeLabel(30);
    JLabel errorLabel = makeLabel(34);

    String screen = "START";
    String screenBeforeError = "START";
    Ticket ticket;
    int dateIndex = 0;
    int slotIndex = 0;
    int typeIndex = 0;                    // highlighted ticket type on the start screen (0 = ticket 1)
    boolean cameraReady = false;          // the gesture camera reports "status:gesture_ready"
    String cameraProblem = null;          // set when the camera / Python could not start
    static final int TYPE_COUNT = 5;      // ticket types 1..5 in ContentProvider
    Timer timer;

    public MainFrame() {
        setTitle("Museum Ticket Kiosk");
        setSize(1200, 700);
        setLocationRelativeTo(null);
        setDefaultCloseOperation(EXIT_ON_CLOSE);

        errorLabel.setForeground(new Color(160, 0, 0));

        root.add(startLabel, "START");
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

    void handleKey(int key) {
        if (key == KeyEvent.VK_1) handle("marker", "1");
        if (key == KeyEvent.VK_2) handle("marker", "2");
        if (key == KeyEvent.VK_3) handle("marker", "3");
        if (key == KeyEvent.VK_4) handle("marker", "4");
        if (key == KeyEvent.VK_5) handle("marker", "5");
        if (key == KeyEvent.VK_LEFT) handle("gesture", "swipe_left");
        if (key == KeyEvent.VK_RIGHT) handle("gesture", "swipe_right");
        if (key == KeyEvent.VK_ENTER) handle("gesture", "raise_hand");
        if (key == KeyEvent.VK_ESCAPE) handle("gesture", "cross_arms");
        if (key == KeyEvent.VK_X) handle("gesture", "unknown");
    }

    public void handle(String type, String value) {
        if (type.equals("status")) {
            if (value.equals("gesture_ready")) {
                cameraReady = true;
                cameraProblem = null;
            } else if (value.startsWith("problem:")) {
                cameraReady = false;
                cameraProblem = value.substring("problem:".length());
            }
            if (screen.equals("START")) {
                showStartScreen();
            }
            return;
        }
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
        if (screen.equals("SUMMARY")) {
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
        showDateScreen();
    }

    void onGesture(String gesture) {
        if (screen.equals("SUMMARY")) {               // booking is done: only "cross arms" (start over) matters
            if (gesture.equals("cross_arms")) {
                goToStart();
            }
            return;
        }
        if (gesture.equals("swipe_right")) {
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
        if (screen.equals("START")) {
            typeIndex = (typeIndex + step + TYPE_COUNT) % TYPE_COUNT;
            showStartScreen();
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
        if (screen.equals("START")) {
            ticket = ContentProvider.getTicket(typeIndex + 1);
            dateIndex = 0;
            slotIndex = 0;
            showDateScreen();
        } else if (screen.equals("DATE")) {
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

    void goToStart() {
        stopTimer();
        ticket = null;
        typeIndex = 0;
        showStartScreen();
    }

    void showStartScreen() {
        String text = "<html><center>Welcome to the museum<br><br>Choose your ticket type<br><br>";
        for (int i = 0; i < TYPE_COUNT; i++) {
            String name = ContentProvider.getTicket(i + 1).name;
            if (i == typeIndex) {
                text += "<font color='blue'>&gt; " + name + " &lt;</font><br>";
            } else {
                text += name + "<br>";
            }
        }
        text += "<br><font size='5'>Swipe to change - Raise your hand to confirm</font>";
        if (cameraProblem != null) {
            String safe = cameraProblem.replace("&", "&amp;").replace("<", "&lt;");
            text += "<br><br><div style='width:700px'><font size='5' color='red'>Camera problem: " + safe
                    + "<br>You can still use the arrow keys and Enter.</font></div>";
        } else if (!cameraReady) {
            text += "<br><br><font size='5' color='gray'>Starting camera...</font>";
        }
        text += "</center></html>";
        startLabel.setText(text);
        show("START");
    }

    void show(String name) {
        screen = name;
        cards.show(root, name);
        if (CameraManager.instance != null && !name.equals("ERROR")) {
            CameraManager.instance.onScreen(name);
        }
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
