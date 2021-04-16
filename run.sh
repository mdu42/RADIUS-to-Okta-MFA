#!/bin/sh

export OKTA_TENANT=yourtenant.okta.com
export OKTA_API_KEY=XXXXXX
export RADIUS_SECRET=******
export RADIUS_PORT=1812
export OKTA_WKF_ASYNC_MFA_CREATE_TRANSACTION_URL="https://yourtenant.workflows.okta.com/api/flo/7e23559648a5ee6d44cadd396765440e/invoke?clientToken=xxxxxxxxxx"
export OKTA_WKF_ASYNC_MFA_POLL_TRANSACTION_URL="https://yourtenant.workflows.okta.com/api/flo/f42993a52f64df3073ab25a9997f8777/invoke?clientToken=xxxxxxxxxxx&transactionId="

p=$(which python3)
$p server.py