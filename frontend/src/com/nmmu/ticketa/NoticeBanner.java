package src.com.nmmu.ticketa;

import java.awt.Color;
import java.awt.Font;
import java.awt.Point;
import javax.swing.BorderFactory;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JWindow;
import javax.swing.SwingConstants;
import javax.swing.Timer;

/**
 * Banner along the bottom of the kiosk for "notice:<text>" messages
 * (wheelchairs, watch your children, take care of your items).
 * It is its own small window, so it does not touch MainFrame's screens,
 * and it never takes keyboard focus. Call show() on the Swing thread.
 */
public class NoticeBanner {

    private static final int HEIGHT = 90;
    private static final int SHOW_MS = 7000;

    private final JFrame owner;
    private final JWindow window;
    private final JLabel label = new JLabel("", SwingConstants.CENTER);
    private final Timer hideTimer;

    public NoticeBanner(JFrame owner) {
        this.owner = owner;
        window = new JWindow(owner);
        window.setFocusableWindowState(false);          // keep keys going to the kiosk
        label.setFont(new Font("SansSerif", Font.BOLD, 30));
        label.setForeground(Color.WHITE);
        label.setBorder(BorderFactory.createEmptyBorder(10, 20, 10, 20));
        window.getContentPane().setBackground(new Color(30, 60, 120));
        window.getContentPane().add(label);
        hideTimer = new Timer(SHOW_MS, e -> window.setVisible(false));
        hideTimer.setRepeats(false);
    }

    public void show(String text) {
        if (!owner.isShowing()) {
            return;
        }
        String safe = text.replace("&", "&amp;").replace("<", "&lt;");
        label.setText("<html><center>" + safe + "</center></html>");
        Point p = owner.getLocationOnScreen();
        window.setBounds(p.x, p.y + owner.getHeight() - HEIGHT, owner.getWidth(), HEIGHT);
        window.setVisible(true);
        hideTimer.restart();                            // a new notice restarts the 7 seconds
    }
}
