import curses
from datetime import datetime
import logging

import shared_cfg
import hardware

CW_ORDER = [1, 3, 0, 2]
CCW_ORDER = [2, 0, 3, 1]

# Button label positions are determined empirically and are dependent on
# character resolution.
# Dictionary key is max x character position.
BTN_LABEL_X_POS = {
    40: [3, 15, 26, 37],
    120: [3, 15, 26, 37]
}

log = logging.getLogger(__name__)


class Extent:
    def __init__(self, min, max):
        self.min = min
        self.max = max

    def span(self):
        return self.max - self.min + 1


class StoreNavigator:
    """Renders current view of password store"""
    def __init__(self, min_col, min_row, max_col, max_row):
        self.level = "/"
        self.level_container = None # Container of current_level
        self.selection = 0  # index of current selection
        self.top_row_index = 0    # index of top visible row
        self.col_extent = Extent(min_col, max_col)
        self.row_extent = Extent(min_row, max_row)
        self.level_container_names = []
        self.level_entry_names = []
        log.debug("New navigator: min_row: {0}  max_row: {1}  vis_rows: {2}\n"
                  "min_col: {3}  max_col: {4}  vis_cols: {5}"
                  .format(min_row, max_row, self.row_extent.span(),
                          min_col, max_col, self.col_extent.span()))
        self.change_level(0)

    def change_level(self, direction):
        if direction < 0: # Drilling down to the currently-selected level
            name, is_cont = self.get_selection()
            if not is_cont:
                return
            self.level += "/" + name
        elif direction > 0 and not self.level == "/": # Popping up to parent level
            last_slash = self.level.rindex("/")
            self.level = self.level[0:last_slash]

        self.level_container = shared_cfg.master_store.get_container_by_path(self.level)

        self.level_container_names = []
        self.level_entry_names = []
        for k, c in self.level_container.get_containers():
            self.level_container_names.append(k)
        for k, e in self.level_container.get_entries():
            self.level_entry_names.append(k)
        self.level_container_names.sort()
        self.level_entry_names.sort()
        self.selection = 0

    def get_selection(self):
        """
        :return: Returns a tuple, containing the name of current selection and
        a boolean indicating whether or not the selection is a container.
        """
        cc = len(self.level_container_names)
        ec = len(self.level_entry_names)

        if cc == 0 and ec == 0:
            return "", False

        if self.selection >= cc:
            return self.level_entry_names[self.selection - cc], False
        return self.level_container_names[self.selection], True

    def change_selection(self, stdscr, direction):
        """

        :type direction: int
        """
        cc = self.level_container.get_container_count()
        ec = self.level_container.get_entry_count()

        if self.selection <= 0 and direction < 0:
            return self.selection
        if self.selection >= cc + ec - 1 and direction > 0:
            return self.selection

        self.selection += direction
        if self.selection < self.top_row_index:
            self.top_row_index -= 1
        if self.selection >= self.top_row_index + self.row_extent.span():
            self.top_row_index += 1

        for r in range(self.top_row_index, self.top_row_index + self.row_extent.span()):
            scr_row = self.row_extent.min + r - self.top_row_index
            scr_col = self.col_extent.min
            entry_text = ""
            if r < cc:
                entry_text = ">" + self.level_container_names[r]
            elif r < cc + ec + 1 and r - cc < ec:
                entry_text = self.level_entry_names[r-cc]
            elif self.selection == 0 and cc + ec == 0 and r == self.top_row_index:
                entry_text = "<<<<NO ENTRIES>>>>"

            if self.selection == r and cc + ec > 0:
                stdscr.addstr(scr_row, scr_col,
                    entry_text.ljust(self.col_extent.span()), curses.A_REVERSE)
            else:
                stdscr.addstr(scr_row, scr_col, entry_text.ljust(self.col_extent.span()))

        return self.selection


def cryptex(stdscr):
    hardware.set_device_mode(shared_cfg.RNDIS_USB_MODE)
    enc_value = hardware.get_enc_value()
    selection = 0
    in_keyboard_mode = False
    navigator = None

    curses.curs_set(0)  # Turn off cursor
    maxy, maxx = stdscr.getmaxyx()
    stdscr.border()

    for x in range(0, maxx):
        stdscr.addstr(maxy - 2, x, "{0}".format(x % 10))
    for b in range(0, 4):
        stdscr.addstr(maxy - 1, BTN_LABEL_X_POS[maxx][b], "{0}".format(b + 1))
    stdscr.refresh()

    try:
        while 1:
            row = 1
            if shared_cfg.is_in_keyboard_mode():
                stdscr.addstr(row, 1, "Navigate entries w/jog wheel".ljust(maxx-2))
            elif shared_cfg.master_store:
                stdscr.addstr(row, 1, "In web browser mode".ljust(maxx-2))
            else:
                stdscr.addstr(row, 1, "Log in to https://cryptex/login".ljust(maxx-2))
            row += 1
            stdscr.addstr(row, 1,
                          "{0}".format(
                              datetime.now().strftime("%Y %m %d %H:%M:%S")).ljust(maxx-2))
            row += 1

            new_enc_value, eb_pressed, hw_button = hardware.check_gpio(enc_value)

            direction = 0
            if new_enc_value != enc_value:
                if new_enc_value == CW_ORDER[enc_value]:
                    direction = 1
                elif new_enc_value == CCW_ORDER[enc_value]:
                    direction = -1
                enc_value = new_enc_value
            stdscr.addstr(row, 1, "Selection: {0:<5}".format(selection).ljust(maxx-2))
            row += 1
            stdscr.addstr(row, 1, "PW store loaded: {0}".format(
                "Yes" if shared_cfg.master_store else "No ").ljust(maxx-2))
            row += 1
            stdscr.addstr(row, 1, "Screen dimensions: {0} x {1}".format(maxx, maxy).ljust(maxx-2))
            row += 1

            if shared_cfg.is_in_keyboard_mode():
                if not in_keyboard_mode:
                    in_keyboard_mode = True
                    navigator = StoreNavigator(1, row, maxx-2, row+5)
                selection = navigator.change_selection(stdscr, direction)
                if eb_pressed:
                    navigator.change_level(-1)
                elif hw_button == 1:
                    navigator.change_level(1)


            stdscr.refresh()
    except KeyboardInterrupt:
        hardware.GPIO.cleanup()
