# Copyright (C) 2024, Manuel Genovés <manuel.genoves@gmail.com>
#                     Fina Wilke <code@felinira.net>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
# END LICENSE

# Code adapted from Warp: <https://gitlab.gnome.org/World/warp/>


from enum import Enum
from datetime import datetime

class Season(Enum):
    INTERSEX = "intersex"
    LESBIAN = "lesbian"
    AIDS = "aids"
    AUTISM = "autism"
    PAN = "pan"
    TRANS = "trans"
    ARO = "aro"
    ACE = "ace"
    BI = "bi"
    NON_BINARY = "non-binary"
    PRIDE = "pride"
    DISABILITY = "disability"
    BLACK_HISTORY = "black-history"

    def __str__(self):
        return self.value

    @classmethod
    def all(cls):
        return list(cls)

    def is_season(self, date):
        match self:
            case Season.INTERSEX:
                return (date.month == 10 and date.day == 26) or (date.month == 11 and date.day == 8)
            case Season.LESBIAN:
                return (date.month == 10 and date.day == 8) or \
                    (date.month == 4 and date.day >= 26) or \
                    (date.month == 5 and date.day <= 2)
            case Season.AIDS:
                return date.month == 12 and date.day == 1
            case Season.AUTISM:
                return date.month == 6 and date.day == 18
            case Season.PAN:
                return date.month == 5 and date.day == 24
            case Season.TRANS:
                return (date.month == 11 and 13 <= date.day <= 19) or \
                    (date.month == 11 and date.day == 20) or \
                    (date.month == 3 and date.day == 31)
            case Season.ARO:
                february_14 = datetime(date.year, 2, 14)
                weekday_offset = february_14.weekday()
                start = 14 + 7 - weekday_offset
                end = start + 6
                return date.month == 2 and start <= date.day <= end
            case Season.ACE:
                last_day_october = datetime(date.year, 10, 31)
                weekday_offset_last_day_october = last_day_october.weekday()
                start = 31 - 7 if weekday_offset_last_day_october == 6 else 31 - weekday_offset_last_day_october - 7
                end = start + 6
                return date.month == 10 and start <= date.day <= end
            case Season.BI:
                return date.month == 9 and 16 <= date.day <= 23
            case Season.NON_BINARY:
                july_14 = datetime(date.year, 7, 14)
                weekday_july_14_offset = july_14.weekday()
                start = 14 - weekday_july_14_offset
                end = start + 7
                return date.month == 7 and start <= date.day <= end
            case Season.PRIDE:
                return date.month == 6
            case Season.DISABILITY:
                return date.month == 7
            case Season.BLACK_HISTORY:
                return date.month in [2, 10]

    @classmethod
    def for_date(cls, date):
        return next((season for season in cls.all() if season.is_season(date)), None)

    @classmethod
    def current(cls):
        return cls.for_date(datetime.now())

def css_class(season):
    return f"flag-{season}"

def apply_seasonal_style(widget):
    for season in Season.all():
        widget.remove_css_class(css_class(season))

    current_season = Season.current()
    if current_season:
        print(f"Adding pride CSS class {css_class(current_season)}")
        widget.add_css_class(css_class(current_season))
