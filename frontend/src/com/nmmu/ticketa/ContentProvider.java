package src.com.nmmu.ticketa;
public class ContentProvider {

    public static String[] times = {"09:00 AM", "10:45 AM", "12:30 PM", "02:15 PM"};
    public static int[] seats = {12, 6, 20, 0};

    public static Ticket getTicket(int markerId) {
        if (markerId == 1) {
            return new Ticket("Egyptian Adult", "Price: 100 EGP", "Show your national ID at the entrance");
        }
        if (markerId == 2) {
            return new Ticket("Student", "Price: 50 EGP", "Show your student ID at the entrance");
        }
        if (markerId == 3) {
            return new Ticket("Foreign Adult", "Price: 600 EGP", "Photography rules apply inside the galleries");
        }
        if (markerId == 4) {
            return new Ticket("Child", "Price: 30 EGP", "A guardian must enter with the child");
        }
        if (markerId == 5) {
            return new Ticket("Elderly", "Price: 50 EGP", "Show your ID at the entrance");
        }
        return null;
    }
}
