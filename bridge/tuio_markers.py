"""
TUIO marker detection (Lab 3) -> ticket type.

reacTIVision sends TUIO 1.1 messages as OSC over UDP (127.0.0.1:3333).
Lab 3 did this in C# with the TUIO/OSC.NET classes; here it is the same idea in
plain Python (standard library only, nothing to pip install):

    /tuio/2Dobj set   s_id i_id x y a ...   <- a marker is on the table (i_id = marker ID)
    /tuio/2Dobj alive s_id s_id ...         <- which sessions are still on the table

Like addTuioObject() in Lab 3's Program.cs, we react ONCE when a marker appears,
not on every update, so one placed card = one "marker:<id>" message.
"""
import socket
import struct
import threading
import time

# Marker ID -> ticket type. Must match ContentProvider.getTicket() on the Java side.
TICKET_TYPES = {
    1: "Egyptian Adult",
    2: "Student",
    3: "Foreign Adult",
    4: "Child",
    5: "Elderly",
}

# WHICH PHYSICAL MARKER IS WHICH TICKET.  <printed marker ID>: <ticket ID 1-5>
# 1 Egyptian Adult, 2 Student, 3 Foreign Adult, 4 Child, 5 Elderly.
# Put the IDs of the markers you actually have here (the bridge prints the ID when you show one).
MARKER_MAP = {
    11: 1,
    0: 2,
}

# Notice shown on the kiosk when a marker is placed (sent as "notice:<text>").
# Keep the text on ONE line. Change the wording here, nothing else needs touching.
NOTICE_WHEELCHAIRS = "Wheelchairs are available."
NOTICE_CHILDREN = "5odo balko mn 3yalko"
NOTICE_ITEMS = "Please take care of your items."

NOTICES = {
    1: NOTICE_ITEMS,          # Egyptian Adult
    2: NOTICE_ITEMS,          # Student
    3: NOTICE_ITEMS,          # Foreign Adult
    4: NOTICE_CHILDREN,       # Child
    5: NOTICE_WHEELCHAIRS,    # Elderly
}


def notice_for(marker_id):
    """Notice text for a marker ID, or None (unknown markers get no notice)."""
    try:
        return NOTICES.get(int(marker_id))
    except (TypeError, ValueError):
        return None


# ---------- minimal OSC parser (what OSC.NET did in Lab 3) ----------

def _read_string(data, pos):
    end = data.index(b"\x00", pos)
    text = data[pos:end].decode("ascii", errors="replace")
    return text, (end + 4) & ~3          # OSC strings are padded to 4 bytes


def parse_osc(data):
    """Return a list of (address, [args]) from an OSC message or bundle."""
    if data.startswith(b"#bundle"):
        messages = []
        pos = 16                          # "#bundle\0" (8) + time tag (8)
        while pos + 4 <= len(data):
            size = struct.unpack(">i", data[pos:pos + 4])[0]
            pos += 4
            messages += parse_osc(data[pos:pos + size])
            pos += size
        return messages

    address, pos = _read_string(data, 0)
    if pos >= len(data) or data[pos:pos + 1] != b",":
        return [(address, [])]
    tags, pos = _read_string(data, pos)
    args = []
    for tag in tags[1:]:
        if tag == "i":
            args.append(struct.unpack(">i", data[pos:pos + 4])[0]); pos += 4
        elif tag == "f":
            args.append(struct.unpack(">f", data[pos:pos + 4])[0]); pos += 4
        elif tag == "s":
            text, pos = _read_string(data, pos); args.append(text)
        else:
            break                         # type we do not need
    return [(address, args)]


# ---------- marker tracking ----------

class TuioMarkerSource(threading.Thread):
    """Listens to reacTIVision and calls publish("marker", "<id>") when a marker is placed."""

    def __init__(self, publish, host="127.0.0.1", port=3333, cooldown=1.5):
        super().__init__(daemon=True)
        self.publish = publish
        self.host, self.port = host, port
        self.cooldown = cooldown          # ignore the same marker re-appearing within this time
        self.sessions = {}                # TUIO session id -> marker id (markers on the table now)
        self.last_fired = {}              # marker id -> time of the last message
        self.running = True

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.settimeout(0.5)              # wake up so we can stop cleanly
        print(f"[TUIO] listening for reacTIVision on udp://{self.host}:{self.port}")
        while self.running:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                for address, args in parse_osc(data):
                    self._handle(address, args)
            except (ValueError, struct.error, IndexError):
                pass                      # ignore a malformed packet
        sock.close()

    def stop(self):
        self.running = False

    def _handle(self, address, args):
        if address != "/tuio/2Dobj" or not args:
            return
        if args[0] == "set" and len(args) >= 3:
            session_id, marker_id = args[1], args[2]
            if session_id not in self.sessions:          # new marker on the table
                self.sessions[session_id] = marker_id
                self._marker_added(marker_id)
        elif args[0] == "alive":
            alive = set(args[1:])
            for session_id in list(self.sessions):
                if session_id not in alive:              # marker taken away
                    marker_id = self.sessions.pop(session_id)
                    print(f"[TUIO] marker {marker_id} removed")

    def _marker_added(self, marker_id):
        now = time.time()
        if now - self.last_fired.get(marker_id, 0) < self.cooldown:
            return                                       # lost-and-found flicker, not a new card
        self.last_fired[marker_id] = now
        ticket_id = MARKER_MAP.get(marker_id, marker_id)     # printed marker -> ticket ID the kiosk knows
        ticket = TICKET_TYPES.get(ticket_id)
        if ticket:
            print(f"[TUIO] marker {marker_id} placed -> {ticket}")
        else:
            print(f"[TUIO] marker {marker_id} placed -> no ticket type (add it to MARKER_MAP)")
        self.publish("marker", str(ticket_id))
