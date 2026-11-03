package src.com.nmmu.ticketa;

import javax.swing.SwingUtilities;

public class Main {

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            CameraManager.instance = new CameraManager();
            MainFrame frame = new MainFrame();
            frame.setVisible(true);
            CameraManager.instance.setProblemListener(message ->
                    SwingUtilities.invokeLater(() -> frame.handle("status", "problem:" + message)));
            new AdminFrame().setVisible(true);

            NoticeBanner banner = new NoticeBanner(frame);
            ScanStation station = new ScanStation(frame);
            ScanStation.instance = station;
            Runtime.getRuntime().addShutdownHook(new Thread(() -> CameraManager.instance.stopAll()));

            SocketServer server = new SocketServer(5055, (type, value) -> SwingUtilities.invokeLater(() -> {
                if (type.equals("notice")) {
                    banner.show(value);
                } else if (type.equals("marker") && station.isScanning()) {
                    station.onMarker(value);
                } else {
                    frame.handle(type, value);
                }
            }));
            server.start();
        });
    }
}
