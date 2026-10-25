"""Optional check for a newer GitHub release. Never downloads or installs anything."""
import json
import logging
import re
import threading
import urllib.request

from lantern import VERSION

log = logging.getLogger(__name__)
RELEASES_URL = 'https://api.github.com/repos/kevincaron28/Lantern-Deck/releases/latest'


def parse_version(text):
    match = re.search(r'(\d+)(?:\.(\d+))?(?:\.(\d+))?', text or '')
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def fetch_latest(url=RELEASES_URL):
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json',
                                                   'User-Agent': f'LanternDeck/{VERSION}'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def compare(release, current=VERSION):
    latest = parse_version(release.get('tag_name', ''))
    if latest is None:
        return None
    url = release.get('html_url', '')
    if not url.startswith('https://github.com/'):
        url = 'https://github.com/kevincaron28/Lantern-Deck/releases'
    return {'latest': '.'.join(map(str, latest)), 'url': url, 'available': latest > parse_version(current)}


class UpdateChecker:
    def __init__(self, fetch=fetch_latest, on_result=None):
        self.fetch, self.on_result = fetch, on_result
        self.result = None

    def start(self):
        threading.Thread(target=self._run, name='updates', daemon=True).start()

    def _run(self):
        try:
            self.result = compare(self.fetch())
            if self.result and self.result['available']:
                log.info('Lantern Deck %s is available', self.result['latest'])
        except (OSError, ValueError) as exc:
            log.info('Update check skipped: %s', type(exc).__name__)
        if self.on_result:
            self.on_result()
