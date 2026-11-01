package src.com.nmmu.ticketa;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.ServerSocket;
import java.net.Socket;
import javax.swing.SwingUtilities;

public class Main {

    public static void main(String[] args) {
        MainFrame frame = new MainFrame();
        frame.setVisible(true);
        new Thread(() -> listen(frame)).start();
    }

    static void listen(MainFrame frame) {
        try {
            ServerSocket server = new ServerSocket(5000);
            while (true) {
                Socket client = server.accept();
                BufferedReader in = new BufferedReader(new InputStreamReader(client.getInputStream()));
                String line;
                while ((line = in.readLine()) != null) {
                    String[] parts = line.trim().split(":");
                    if (parts.length == 2) {
                        String type = parts[0].trim();
                        String value = parts[1].trim();
                        SwingUtilities.invokeLater(() -> frame.handle(type, value));
                    }
                }
            }
        } catch (Exception e) {
            System.out.println("Socket stopped: " + e.getMessage());
        }
    }
}
