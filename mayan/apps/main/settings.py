"""Configuration options for the main app"""

from django.utils.translation import ugettext_lazy as _
from smart_settings.api import register_setting, register_settings

register_setting(
    namespace=u'main',
    module=u'main.settings',
    name=u'DISABLE_HOME_VIEW',
    global_name=u'MAIN_DISABLE_HOME_VIEW',
    default=False,
)

register_setting(
    namespace=u'main',
    module=u'main.settings',
    name=u'DISABLE_ICONS',
    global_name=u'MAIN_DISABLE_ICONS',
    default=False,
)

register_settings(
    namespace=u'main',
    module=u'main.settings',
    settings=[
        {'name': u'ENABLE_SCROLL_JS', 'global_name': u'MAIN_ENABLE_SCROLL_JS', 'default': True, 'hidden': True},
    ]
)
