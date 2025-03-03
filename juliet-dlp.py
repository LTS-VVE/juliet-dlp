import curses
from curses import wrapper
import subprocess
import yt_dlp
from urllib.parse import quote_plus
import textwrap
import threading
from queue import Queue

SPLASH = [
    "     ██ ██    ██ ██      ██ ███████ ████████       ██████  ██      ██████  ",
    "     ██ ██    ██ ██      ██ ██         ██          ██   ██ ██      ██   ██ ",
    "     ██ ██    ██ ██      ██ █████      ██    █████ ██   ██ ██      ██████  ",
    "██   ██ ██    ██ ██      ██ ██         ██          ██   ██ ██      ██      ",
    " █████   ██████  ███████ ██ ███████    ██          ██████  ███████ ██      "
]

class VideoBrowser:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_tab = 0  # 0=Trending, 1=Search
        self.search_query = ""
        self.search_results = []
        self.trending_videos = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.search_mode = False
        self.loading = False
        self.result_queue = Queue()
        self.trending_page = 1
        self.search_page = 1
        self.init_ui()
        
    def init_ui(self):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        self.fetch_trending()

    def fetch_trending(self):
        def worker():
            try:
                with yt_dlp.YoutubeDL({
                    'quiet': True,
                    'extract_flat': True,
                    'force_generic_extractor': True,
                }) as ydl:
                    result = ydl.extract_info(
                        'https://www.youtube.com/feed/trending',
                        download=False
                    )
                    # Directly load first 50 trending videos
                    self.trending_videos = result.get('entries', [])[:50]
                    self.result_queue.put(('trending', True))
            except Exception as e:
                self.result_queue.put(('trending', False))

        self.loading = True
        threading.Thread(target=worker, daemon=True).start()

    def search_videos(self, query):
        def worker():
            try:
                with yt_dlp.YoutubeDL({
                    'quiet': True,
                    'extract_flat': True,
                    'force_generic_extractor': True,
                    'playliststart': (self.search_page - 1) * 50 + 1,
                    'playlistend': self.search_page * 50
                }) as ydl:
                    result = ydl.extract_info(
                        f'https://www.youtube.com/results?search_query={quote_plus(query)}&sp=EgIQAQ%253D%253D',
                        download=False
                    )
                    new_results = result.get('entries', [])[:50]
                    existing_ids = {v['id'] for v in self.search_results}
                    self.search_results += [
                        v for v in new_results
                        if v['id'] not in existing_ids
                    ]
                    self.result_queue.put(('search', True))
            except Exception as e:
                self.result_queue.put(('search', False))

        self.loading = True
        threading.Thread(target=worker, daemon=True).start()

    def draw_ui(self):
        self.stdscr.erase()
        self.draw_splash()
        self.draw_border()
        self.draw_tabs()
        self.draw_search_bar()
        self.draw_video_list()
        self.draw_loading()
        self.stdscr.refresh()

    def draw_border(self):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.border()
        help_text = " TAB: Switch | /: Search | ↑↓: Navigate | ENTER: Play | Q: Quit "
        self.stdscr.addstr(h-1, 2, help_text, curses.color_pair(3) | curses.A_REVERSE)

    def draw_tabs(self):
        tabs = [
            f"🔥 Trending ({len(self.trending_videos)})",
            f"🔍 Search Results (Page {self.search_page})"
        ]
        
        for i, label in enumerate(tabs):
            x = 2 + i*30
            attr = curses.color_pair(1) | curses.A_BOLD if self.current_tab == i else curses.A_DIM
            self.stdscr.addstr(5, x, label, attr)

    def draw_splash(self):
        for i, line in enumerate(SPLASH):
            if i < self.stdscr.getmaxyx()[0]:
                self.stdscr.addstr(i, 0, line, curses.color_pair(1))

    def draw_search_bar(self):
        h, w = self.stdscr.getmaxyx()
        prompt = "🔍 Search: "
        if 7 < h:
            self.stdscr.addstr(7, 2, prompt, curses.A_BOLD)
            max_query_length = w - len(prompt) - 3
            display_query = self.search_query[-max_query_length:] if self.searcsh_mode else ""
            self.stdscr.addstr(7, 2 + len(prompt), 
                display_query.ljust(max_query_length),
                curses.A_REVERSE if self.search_mode else curses.color_pair(2))

    def draw_video_list(self):
        h, w = self.stdscr.getmaxyx()
        videos = self.trending_videos if self.current_tab == 0 else self.search_results
        start_y = 9
        max_items = h - start_y - 2 if h > start_y + 2 else 0
        
        # Ensure selected index stays in bounds
        self.selected_idx = min(self.selected_idx, len(videos)-1) if videos else 0
        
        # Calculate scroll offset
        if self.selected_idx >= self.scroll_offset + max_items:
            self.scroll_offset = self.selected_idx - max_items + 1
        elif self.selected_idx < self.scroll_offset:
            self.scroll_offset = max(0, self.selected_idx)
            
        for i in range(max_items):
            vid_idx = i + self.scroll_offset
            if vid_idx >= len(videos):
                break
            
            y = start_y + i
            if y >= h - 1:
                break
            
            video = videos[vid_idx]
            title = textwrap.shorten(video.get('title', 'Untitled'), 
                                   width=w-10, 
                                   placeholder="...")
            line = f"▶ {vid_idx+1:2d}. {title}"
            attr = curses.color_pair(1) if vid_idx == self.selected_idx else curses.A_NORMAL
            
            self.stdscr.addstr(y, 4, line, attr)
            
            duration = video.get('duration_string') or '--:--'
            channel = textwrap.shorten(video.get('channel', 'Unknown'), 15, placeholder="..")
            self.stdscr.addstr(y, w-25, f"📺 {channel}", curses.A_DIM)
            self.stdscr.addstr(y, w-10, f"⏳ {duration}", curses.A_DIM)

        # Load more indicator only for search
        if self.current_tab == 1 and len(self.search_results) >= 50 * self.search_page:
            if h-3 > 0 and h-3 < h:
                self.stdscr.addstr(h-3, 2, "↓ Scroll down to load more results ↓", curses.color_pair(2))

    def draw_loading(self):
        if self.loading:
            h, w = self.stdscr.getmaxyx()
            if h-2 > 0 and h-2 < h:
                self.stdscr.addstr(h-2, 2, "🌀 Loading more results...", curses.color_pair(2))

    def play_selected(self):
        videos = self.trending_videos if self.current_tab == 0 else self.search_results
        if not videos or self.selected_idx >= len(videos):
            return
            
        video = videos[self.selected_idx]
        try:
            subprocess.Popen(
                ['mpv', '--no-terminal', '--force-window', video['url']],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            pass

    def handle_input(self):
        key = self.stdscr.getch()
        
        if self.search_mode:
            if key in [curses.KEY_ENTER, 10, 13]:
                self.search_mode = False
                if self.search_query:
                    self.search_results = []
                    self.search_page = 1
                    self.selected_idx = 0
                    self.scroll_offset = 0
                    self.search_videos(self.search_query)
                curses.noecho()
            elif key in [curses.KEY_BACKSPACE, 127, 8]:
                self.search_query = self.search_query[:-1]
            elif 32 <= key <= 126:
                self.search_query += chr(key)
            return True
        
        if key == ord('q'):
            return False
        elif key == curses.KEY_UP:
            self.selected_idx = max(0, self.selected_idx - 1)
        elif key == curses.KEY_DOWN:
            videos = self.trending_videos if self.current_tab == 0 else self.search_results
            if videos:
                self.selected_idx = min(len(videos)-1, self.selected_idx + 1)
                
                # Auto-load more only for search results
                if self.current_tab == 1 and self.selected_idx >= len(videos) - 3:
                    self.search_page += 1
                    self.search_videos(self.search_query)
        elif key in [curses.KEY_ENTER, 10, 13]:
            self.play_selected()
        elif key == ord('\t'):
            self.current_tab = (self.current_tab + 1) % 2
            self.selected_idx = 0
            self.scroll_offset = 0
        elif key == ord('/'):
            self.search_mode = True
            self.search_query = ""
            curses.curs_set(1)
        
        return True

    def run(self):
        while True:
            self.draw_ui()
            
            while not self.result_queue.empty():
                result_type, success = self.result_queue.get()
                self.loading = False
            
            self.stdscr.timeout(100)
            if not self.handle_input():
                break

def main(stdscr):
    browser = VideoBrowser(stdscr)
    browser.run()

if __name__ == '__main__':
    wrapper(main)
