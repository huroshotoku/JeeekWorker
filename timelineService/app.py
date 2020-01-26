import os
from flask import Flask, request
import logging
import json
import base64

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from google.auth.transport import requests
from google.oauth2 import id_token


app = Flask(__name__)

# Use the application default credentials
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
  'projectId': os.environ['PROJECT_ID'],
})
db = firestore.client()

logging.basicConfig(level=logging.DEBUG)


@app.route('/')
def health_check():
    logging.debug('timeline.service: /')
    return 'OK!', 200


@app.route('/writer', methods=['POST'])
def timeline_writer():
    logging.info('timeline.service: /writer')

    # Verify that the push request originates from Cloud Pub/Sub.
    try:
        # Get the Cloud Pub/Sub-generated JWT in the "Authorization" header.
        bearer_token = request.headers.get('Authorization')
        token = bearer_token.split(' ')[1]

        claim = id_token.verify_oauth2_token(token, requests.Request(),
                                             audience='example.com')

        # Verify administrator rights
        if claim['sub'] != os.environ['ADMIN_UID']:
            logging.error('Error: you do not have administrator right.')

        # Must also verify the `iss` claim.
        if claim['iss'] not in [
            'accounts.google.com',
            'https://accounts.google.com'
        ]:
            raise ValueError('Wrong issuer.')
    except Exception as e:
        logging.error(e)
        return 'Invalid token: {}\n'.format(e), 400

    envelope = json.loads(request.data.decode('utf-8'))
    payload = base64.b64decode(envelope['message']['data'])
    payload = json.loads(payload.decode())

    target_user = envelope['message']['attributes']['uid']

    activity_id = payload['ID']
    del payload['ID']

    doc_ref = db.collection(u'users').document(target_user)\
        .collection(u'timeline').document(activity_id)
    doc_ref.set(payload)

    logging.info('timeline.service: /writer={'+activity_id+', '+target_user+'} is complete.')
    return 'OK', 200


@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
