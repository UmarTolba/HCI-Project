package src.com.nmmu.ticketa;

import javax.swing.SwingUtilities;

public class Main {

    public static void main(String[] args) {
        MainFrame frame = new MainFrame();
        frame.setVisible(true);
        NoticeBanner banner = new NoticeBanner(frame);
        ScanStation station = new ScanStation(frame);
        ScanStation.instance = station;
        Runtime.getRuntime().addShutdownHook(new Thread(station::stopCamera));   // close reacTIVision with the app

        // Receives "marker:<id>", "gesture:<name>" and "notice:<text>" lines from bridge/bridge.py
        SocketServer server = new SocketServer(5000, (type, value) -> SwingUtilities.invokeLater(() -> {
            if (type.equals("notice")) {
                banner.show(value);
            } else if (type.equals("marker") && station.isScanning()) {
                station.onMarker(value);                // scanning a printed ticket, not starting a reservation
            } else {
                frame.handle(type, value);
            }
        }));
        server.start();
    }
}
