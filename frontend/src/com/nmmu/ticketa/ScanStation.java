package src.com.nmmu.ticketa;

import java.awt.Font;
import java.awt.Point;
import javax.swing.JButton;
import javax.swing.JDialog;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.SwingConstants;
import javax.swing.BorderFactory;
import java.awt.BorderLayout;

/**
 * Entrance scan, shown after a ticket is printed.
 *
 *   ticket printed  ->  small window with a "Scan ticket at entrance" button
 *   button pressed  ->  CameraManager opens the TUIO camera (reacTIVision) and waits for the marker on the printed ticket
 *   marker arrives  ->  checks it matches the reserved ticket type; the notice banner
 *                       (wheelchairs / children / items) comes from the bridge's notice message
 *
 * All methods must be called on the Swing thread (Main does that).
 */
public class ScanStation {

    /** MainFrame calls ScanStation.instance.ticketPrinted(...) when the summary is shown. */
    public static ScanStation instance;

    private final JFrame owner;
    private final JDialog dialog;
    private final JLabel label = new JLabel("", SwingConstants.CENTER);
    private final JButton button = new JButton();

    private String code = "";
    private String ticketName = "";
    private boolean scanning = false;
    private boolean verified = false;

    public ScanStation(JFrame owner) {
        this.owner = owner;
        dialog = new JDialog(owner, "Entrance scan", false);
        dialog.setSize(560, 210);
        dialog.setFocusableWindowState(false);          // keep keys going to the kiosk
        label.setFont(new Font("SansSerif", Font.PLAIN, 20));
        button.setFont(new Font("SansSerif", Font.BOLD, 22));
        button.addActionListener(e -> onButton());
        JPanel panel = new JPanel(new BorderLayout(10, 10));
        panel.setBorder(BorderFactory.createEmptyBorder(15, 15, 15, 15));
        panel.add(label, BorderLayout.CENTER);
        panel.add(button, BorderLayout.SOUTH);
        dialog.setContentPane(panel);
    }

    public boolean isScanning() {
        return scanning;
    }

    /** Called by MainFrame right after the ticket code is generated and saved. */
    public void ticketPrinted(String code, String ticketName) {
        stopCamera();
        this.code = code;
        this.ticketName = ticketName;
        scanning = false;
        verified = false;
        setText("Ticket " + code + " (" + ticketName + ") booked.<br>At the entrance, press the button and show your ticket marker to the camera.");
        button.setText("Scan ticket at entrance");
        place();
        dialog.setVisible(true);
    }

    private void onButton() {
        if (verified) {                                 // "Close" after a successful scan
            dialog.setVisible(false);
        } else if (scanning) {                          // "Cancel"
            stopCamera();
            scanning = false;
            setText("Scan cancelled.");
            button.setText("Scan ticket at entrance");
        } else {                                        // "Scan ticket at entrance"
            scanning = true;
            button.setText("Cancel");
            setText("Show the marker on your printed ticket to the camera...");
            if (CameraManager.instance != null) {
                CameraManager.instance.setScanHold(true);   // TUIO camera, even if the kiosk is on another screen
            }
        }
    }

    /** A marker was scanned (ticket ID already mapped by the bridge). */
    public void onMarker(String value) {
        Ticket found = null;
        try {
            found = ContentProvider.getTicket(Integer.parseInt(value.trim()));
        } catch (NumberFormatException e) {
            // found stays null
        }
        if (found == null) {
            setText("Wrong TUIO. This is not a ticket marker.<br>Please try again.");
        } else if (!found.name.equals(ticketName)) {
            setText("Wrong TUIO! This marker is a " + found.name + " ticket, but your reservation is " + ticketName + ".<br>Please try again.");
        } else {
            verified = true;
            scanning = false;
            stopCamera();
            setText("Ticket " + code + " verified.<br>You are a " + ticketName + ". Welcome!");
            button.setText("Close");
        }
    }

    // ---------- camera (opened and closed by CameraManager) ----------

    public void stopCamera() {
        if (CameraManager.instance != null) {
            CameraManager.instance.setScanHold(false);
        }
    }

    // ---------- window ----------

    private void setText(String html) {
        label.setText("<html><center>" + html + "</center></html>");
    }

    private void place() {                              // above the notice banner, centred on the kiosk
        Point p = owner.getLocationOnScreen();
        int x = p.x + (owner.getWidth() - dialog.getWidth()) / 2;
        int y = p.y + owner.getHeight() - 90 - dialog.getHeight() - 15;
        dialog.setLocation(x, y);
    }
}
