package src.com.nmmu.ticketa;

public class ContentProvider {

    // Time slots and matching seat counts used by Person 3's MainFrame
    public static String[] times = {"09:00 AM", "10:45 AM", "12:30 PM", "02:15 PM"};
    public static int[] seats = {12, 6, 20, 0};

    // Content loaded per marker ID (Prices, names, and entrance rules)[cite: 5, 6]
    public static Ticket getTicket(int markerId) {
        switch (markerId) {
            case 1:
                return new Ticket("Egyptian Adult", "Price: 100 EGP", "Show your national ID at the entrance");
            case 2:
                return new Ticket("Student", "Price: 50 EGP", "Show your student ID at the entrance");
            case 3:
                return new Ticket("Foreign Adult", "Price: 600 EGP", "Photography rules apply inside the galleries");
            case 4:
                return new Ticket("Child", "Price: 30 EGP", "A guardian must enter with the child");
            default:
                return null;
        }
    }

    public static String getQueueHint() {
        return "Tip: 12:30 PM currently has the most available seats.";
    }
}