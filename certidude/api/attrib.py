import falcon
import logging
import re
from xattr import setxattr, listxattr, removexattr, getxattr
from certidude import push
from certidude.decorators import serialize, csrf_protection
from .utils.firewall import login_required, authorize_admin, whitelist_subject

logger = logging.getLogger(__name__)

class AttributeResource(object):
    def __init__(self, authority, namespace):
        self.authority = authority
        self.namespace = namespace

    @serialize
    @login_required
    @authorize_admin
    def on_get(self, req, resp, cn):
        """
        Return extended attributes stored on the server.
        This not only contains tags and lease information,
        but might also contain some other sensitive information.
        """
        try:
            path, buf, cert, attribs = self.authority.get_attributes(cn,
                namespace=self.namespace, flat=True)
        except IOError:
            raise falcon.HTTPNotFound()
        else:
            return attribs

    @csrf_protection
    @whitelist_subject
    def on_post(self, req, resp, cn):
        namespace = ("user.%s." % self.namespace).encode("ascii")
        try:
            path, buf, cert, signed, expires = self.authority.get_signed(cn)
        except IOError:
            raise falcon.HTTPNotFound()
        else:
            for key in req.params:
                if not re.match("[a-z0-9_\.]+$", key):
                    raise falcon.HTTPBadRequest("Invalid key %s" % key)
            valid = set()
            modified = False
            for key, value in req.params.items():
                identifier = ("user.%s.%s" % (self.namespace, key)).encode("ascii")
                try:
                    if getxattr(path, identifier).decode("utf-8") != value:
                        modified = True
                except OSError: # no such attribute
                    pass
                setxattr(path, identifier, value.encode("utf-8"))
                valid.add(identifier)
            for key in listxattr(path):
                if not key.startswith(namespace):
                    continue
                if key not in valid:
                    modified = True
                    removexattr(path, key)
            if modified:
                push.publish("attribute-update", cn)

