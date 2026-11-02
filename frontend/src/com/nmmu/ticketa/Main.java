package src.com.nmmu.ticketa;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.ServerSocket;
import java.net.Socket;
import javax.swing.SwingUtilities;

public class Main {

    public static void main(String[] args) {
        // 1. Start Person 3's Kiosk UI
        MainFrame frame = new MainFrame();
        frame.setVisible(true);

        // 2. Start Person 4's Staff Admin Dashboard window
        SwingUtilities.invokeLater(() -> {
            new AdminFrame().setVisible(true);
        });

        // 3. Start the socket listener for gestures and markers
        new Thread(() -> listen(frame)).start();
    }
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