package src.com.nmmu.ticketa;

import java.awt.*;
import java.io.BufferedReader;
import java.io.FileReader;
import javax.swing.*;

public class AdminFrame extends JFrame {
    private JTextArea textArea;

    public AdminFrame() {
        setTitle("Museum Kiosk - Staff Admin");
        setSize(450, 400);
        setLocationRelativeTo(null);
        setDefaultCloseOperation(DISPOSE_ON_CLOSE);
        setLayout(new BorderLayout(5, 5));

        // Text area for data display
        textArea = new JTextArea();
        textArea.setFont(new Font("Monospaced", Font.PLAIN, 12));
        textArea.setEditable(false);
        add(new JScrollPane(textArea), BorderLayout.CENTER);

        // Refresh Button at the bottom
        JButton refreshBtn = new JButton("Refresh Data");
        refreshBtn.setFont(new Font("SansSerif", Font.BOLD, 14));
        refreshBtn.addActionListener(e -> loadData());
        add(refreshBtn, BorderLayout.SOUTH);

        // Initial load
        loadData();
    }

    private void loadData() {
        StringBuilder sb = new StringBuilder();
        
        // 1. Load Seat Availability
        sb.append("=== SEAT AVAILABILITY ===\n");
        for (int i = 0; i < ContentProvider.times.length; i++) {
            String status = ContentProvider.seats[i] == 0 ? " (FULL)" : "";
            sb.append(ContentProvider.times[i]).append(" -> ")
              .append(ContentProvider.seats[i]).append(" seats left").append(status).append("\n");
        }

        // 2. Load Saved Reservations from tickets.txt
        sb.append("\n=== SAVED RESERVATIONS (tickets.txt) ===\n");
        try (BufferedReader br = new BufferedReader(new FileReader("tickets.txt"))) {
            String line;
            int count = 0;
            while ((line = br.readLine()) != null) {
                sb.append(line).append("\n");
                count++;
            }
            sb.insert(0, "Total Bookings: " + count + "\n-------------------------------------\n");
        } catch (Exception e) {
            sb.append("No tickets found yet or file doesn't exist.\n");
        }

        textArea.setText(sb.toString());
    }
}