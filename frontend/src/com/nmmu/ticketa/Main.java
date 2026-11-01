package src.com.nmmu.ticketa;

import javax.swing.SwingUtilities;

public class Main {

    public static void main(String[] args) {
        MainFrame frame = new MainFrame();
        frame.setVisible(true);

        // Receives "marker:<id>" and "gesture:<name>" lines from bridge/bridge.py
        SocketServer server = new SocketServer(5000,
                (type, value) -> SwingUtilities.invokeLater(() -> frame.handle(type, value)));
        server.start();
    }
}
