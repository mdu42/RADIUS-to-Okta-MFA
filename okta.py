import logging

from requests import Session
from requests.compat import urljoin, urlencode, quote
from requests.exceptions import HTTPError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import threading
import queue
import time
import uuid

logger = logging.getLogger(__file__)


def error_handler(resp, *args, **kargs):
    if not resp.ok:
        raise HTTPError(resp.status_code, resp.json(), response=resp)


class ResponseCodes:
    SUCCESS = 1
    FAILURE = 2


class OktaAPI(object):
    def __init__(self, url, key):
        # Sessions are stateless
        self.base_url = "https://{}".format(url)
        self.key = key

        # Retry with backoff in case we get rate limited, otherwise use the error handler
        retry = Retry(total=3, backoff_factor=5, status_forcelist=[429])
        adapter = HTTPAdapter(max_retries=retry)

        session = Session()
        session.headers['Authorization'] = 'SSWS {}'.format(self.key)
        session.headers['Accept'] = 'application/json'
        session.headers['User-Agent'] = 'pyrad/1.0'
        session.hooks = {'response': [error_handler, ]}
        session.mount('https://', adapter)

        self.session = session

    def _get(self, url, params=None):
        r = self.session.get(url, params=params)

        return r.json()

    def _post(self, url, params=None, json=None):
        r = self.session.post(url, params=params, json=json)

        return r.json()

    def get_user_id(self, username):
        url = urljoin(self.base_url, 'api/v1/users/{}'.format(username))

        page = self._get(url)

        return page["id"]

    def get_user_by_samaccountname(self, username):
        data = urlencode({'search': f"profile.samAccountName eq \"{username}\""}, quote_via=quote)
        url = urljoin(self.base_url, f"api/v1/users?{data}")

        page = self._get(url)

        return page[0]["id"]

    def get_user_push_factor(self, user_id):
        url = urljoin(self.base_url, 'api/v1/users/{}/factors'.format(user_id))

        page = self._get(url)

        # Return the first push factorType in the array, otherwise return None (no factor setup)
        try:
            return next(item for item in page if item["factorType"] == "push")
        except StopIteration:
            return None

    def poll_verify(self, url, q):
        t = 0
        while True:
            page = self._get(url)

            if page["factorResult"] == "SUCCESS":
                q.put("SUCCESS")
                return
            elif page["factorResult"] == "REJECTED":
                q.put("FAILED")
                return

            time.sleep(4)
            t += 4

            if t > 60:
                return

    def push_verify(self, user_id, factor_id):
        url = urljoin(self.base_url, 'api/v1/users/{}/factors/{}/verify'.format(user_id, factor_id))

        page = self._post(url)

        poll_url = page["_links"]["poll"]["href"]

        q = queue.Queue()
        thread = threading.Thread(target=self.poll_verify, args=(poll_url, q))
        thread.start()
        thread.join()

        if q.qsize() > 0:
            if q.get() == "SUCCESS":
                return ResponseCodes.SUCCESS

        return ResponseCodes.FAILURE

    def push_async_mfa(self, user_id):
        transactionId = str(uuid.uuid4())
        url = "https://mdu-sbx-o365.workflows.oktapreview.com/api/flo/7e23559648a5ee6d44cadd396765440e/invoke?clientToken=ac19ee833995c4eada34619e146c8cba5ad3796339dba4b4478191979a46e9e0"
        
        page = self._post(url, json = {
            "username": user_id,
            "transactionId": transactionId
        })

        poll_url = "https://mdu-sbx-o365.workflows.oktapreview.com/api/flo/f42993a52f64df3073ab25a9997f8777/invoke?clientToken=81ad990f1f71a193004f2f3d0a8710726b811882a0dcb4fe2852c34cdeba5033&transactionId=" + transactionId

        q = queue.Queue()
        thread = threading.Thread(target=self.poll_verify_async_mfa, args=(poll_url, q))
        thread.start()
        thread.join()

        if q.qsize() > 0:
            if q.get() == "SUCCESS":
                return ResponseCodes.SUCCESS

        return ResponseCodes.FAILURE

    def poll_verify_async_mfa(self, url, q):
        t = 0
        while True:
            page = self._get(url)

            if page["status"] == "VERIFIED":
                q.put("SUCCESS")
                return
            elif page["status"] != "PENDING":
                q.put("FAILED")
                return

            time.sleep(20)
            t += 20

            if t > 100:
                return