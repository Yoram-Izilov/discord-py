from enum import Enum

class Statuses(Enum):
    ALL_ANIME           = 0
    CURRENTLY_WATCHING  = 1
    COMPLETED           = 2
    ON_HOLD             = 3
    DROPPED             = 4
    PLAN_TO_WATCH       = 6

class RouletteObject(Enum):
    name    = 0
    count   = 1

class Colors(Enum):
    blue    = '#66b3ff'
    red     = '#ff9999'
    green   = '#99ff99'
    purple  = '#c2c2f0'
    cyan    = '#2aebe1'
    pink    = '#ff66f7'


CHART_BAR_COLORS        = list(map(lambda x: x.value, Colors)) 
MAX_BAR_CHAR            = int(10)
WINNER_COLOR            = '#FFAA1D'

RSS_URL                 = "https://subsplease.org/rss/?r=1080"  # The URL of the RSS feed

RSS_FILE_PATH           = 'data/rss_data.json'                  # File to store RSS feed subscriptions
MAL_PROFILE_PATH        = 'data/mal_profile.txt'
CONFIG_LOCAL_PATH       = 'config/config-local.json'
CONFIG_PATH             = 'config/config.json'

MAL_STATUSES_FORMAT     = 'data/anime_list/{}.txt'
MAL_LIST_FORMAT         = 'https://myanimelist.net/animelist/{}?status={}'

BOT_CHANNEL_ID          = 571462116612112384                # Channel ID where announcements will be sent
OTAKU_CHANNEL_ID        = 571380049044045826                    # Channel ID where announcements will be sent

DROPDOWN_TEXT_MAX_LEN   = 100   # Discord's limit per string in dropdown
DROPDOWN_MAX_ITEMS      = 25    # Discord's limit per select menu
MAX_LETTERS             = 2000

