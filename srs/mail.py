# This file is part of the "spring relay site / srs" program. It is published
# under the GPLv3.
#
# Copyright (C) 2016 Daniel Troeder (daniel #at# admin-box #dot# com)
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

from django.core.mail import EmailMessage
from django.conf import settings

logger = logging.getLogger("srs")


def send_mail(recipient_list, subject, mail_text, headers=None, cc=None, bcc=None, sender=settings.DEFAULT_FROM_EMAIL):
    emailmsg = EmailMessage(subject=subject,
                            body=mail_text,
                            from_email=sender,
                            to=recipient_list,
                            headers=headers,
                            cc=cc,
                            bcc=bcc)

    emailmsg.send()

    logger.info("sent email from '%s' about '%s' to '%s' and bcc '%s'", sender, subject, recipient_list, bcc)
