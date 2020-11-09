###
#
# Lenovo Redfish examples - import SKLM client/server certificate
# SecureKeyLifecycleManager feature uses centralized SKLM server to provide keys that unlock storage hardware.
# To use this feature, below steps are needed:
#  - Ensure required license has been imported in BMC(XCC)
#  - Configure SKLM Server(s) in BMC(XCC)
#  - Install/import SKLM server certificate in BMC(XCC) which can be downloaded from SKLM server
#  - Generate SKLM client certificate CSR in BMC(XCC)
#  - Sign the CSR with the CA certificate in SKLM server
#  - Import the signed client certificate in BMC(XCC)
#
# Copyright Notice:
#
# Copyright 2020 Lenovo Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
###

import sys, os
import redfish
import json
import lenovo_utils as utils


def lenovo_sklm_certificate_import(ip, login_account, login_password, certtype, certfile):
    """ import SKLM client/server certificate
        :params ip: BMC IP address
        :type ip: string
        :params login_account: BMC user name
        :type login_account: string
        :params login_password: BMC user password
        :type login_password: string
        :params certtype: type of certificate, client or server
        :type certtype: string
        :params certfile: certificate file by user specified
        :type certfile: string
        :returns: returns successful result when succeeded or error message when failed
        """

    result = {}

    # check file existing
    if not os.path.exists(certfile):
        result = {'ret': False, 'msg': "Specified file %s does not exist. Please check your certificate file path." % (certfile)}
        return result

    # Create a REDFISH object
    login_host = "https://" + ip
    REDFISH_OBJ = redfish.redfish_client(base_url=login_host, username=login_account,
                                         password=login_password, default_prefix='/redfish/v1')

    # Login into the server and create a session
    try:
        REDFISH_OBJ.login(auth="session")
    except:
        result = {'ret': False, 'msg': "Please check the username, password, IP is correct\n"}
        return result

    try:
        # Get response_base_url
        response_base_url = REDFISH_OBJ.get('/redfish/v1', None)
        if response_base_url.status != 200:
            error_message = utils.get_extended_error(response_base_url)
            result = {'ret': False, 'msg': "Url '%s' response Error code %s\nerror_message: %s" % (
                '/redfish/v1', response_base_url.status, error_message)}
            return result

        # Get /redfish/v1/Managers
        managers_url = response_base_url.dict['Managers']['@odata.id']
        response_managers_url = REDFISH_OBJ.get(managers_url, None)
        if response_managers_url.status != 200:
            error_message = utils.get_extended_error(response_managers_url)
            result = {'ret': False, 'msg': "Url '%s' response Error code %s\nerror_message: %s" % (
                managers_url, response_managers_url.status, error_message)}
            REDFISH_OBJ.logout()
            return result
 
        # Access /redfish/v1/Managers/1 to check whether SecureKeyLifecycleService is supported or not
        sklm_url = None
        for request in response_managers_url.dict['Members']:
            request_url = request['@odata.id']
            response_url = REDFISH_OBJ.get(request_url, None)
            if response_url.status != 200:
                error_message = utils.get_extended_error(response_url)
                result = {'ret': False, 'msg': "Url '%s' response Error code %s\nerror_message: %s" % (
                    request_url, response_url.status, error_message)}
                REDFISH_OBJ.logout()
                return result
            if 'SecureKeyLifecycleService' in str(response_url.dict):
                sklm_url = response_url.dict['Oem']['Lenovo']['SecureKeyLifecycleService']['@odata.id']
                break

        # Return here when SKLM feature is not supported
        if sklm_url is None:
            result = {'ret': False, 'msg': 'SecureKeyLifecycleManager(SKLM) is not supported.'}
            REDFISH_OBJ.logout()
            return result

        # Use standard API /redfish/v1/CertificateService/CertificateLocations
        if 'CertificateService' in response_base_url.dict:
            request_url = response_base_url.dict['CertificateService']['@odata.id']
            response_url = REDFISH_OBJ.get(request_url, None)
            if response_url.status != 200:
                error_message = utils.get_extended_error(response_url)
                result = {'ret': False, 'msg': "Url '%s' response Error code %s\nerror_message: %s" % (
                    request_url, response_url.status, error_message)}
                return result
            if 'Actions' in response_url.dict and '#CertificateService.ReplaceCertificate' in response_url.dict['Actions']:
                target_url = response_url.dict['Actions']['#CertificateService.ReplaceCertificate']['target']
                # Set request body
                request_body = {'CertificateType':'PEM'}
                request_body['CertificateString'] = read_cert_file_pem(certfile)
                if request_body['CertificateString'] is None:
                    result = {'ret': False,
                              'msg':"Target server required certificate format should be PEM. Please specify correct certificate file."}
                    return result
                # Get https certificate uri to set request body
                sklm_cert_url = None
                if 'CertificateLocations' in response_url.dict:
                    request_url = response_url.dict['CertificateLocations']['@odata.id']
                    response_url = REDFISH_OBJ.get(request_url, None)
                    if response_url.status != 200:
                        error_message = utils.get_extended_error(response_url)
                        result = {'ret': False, 'msg': "Url '%s' response Error code %s\nerror_message: %s" % (
                            request_url, response_url.status, error_message)}
                        return result
                    if 'Links' in response_url.dict and 'Certificates' in response_url.dict['Links']:
                        cert_collection = response_url.dict['Links']['Certificates']
                        for certitem in cert_collection:
                            cert_url = certitem['@odata.id']
                            if 'SecureKeyLifecycleService' not in cert_url:
                                continue
                            if certtype+'certificate' not in cert_url.lower():
                                continue
                            sklm_cert_url = cert_url
                            break
                if sklm_cert_url is None: # create certificate if no existing certificate found
                    if certtype == 'client':
                        sklm_cert_url = '/redfish/v1/Managers/1/Oem/Lenovo/SecureKeyLifecycleService/ClientCertificate'
                    else:
                        sklm_cert_url = '/redfish/v1/Managers/1/Oem/Lenovo/SecureKeyLifecycleService/ServerCertificate'
                    target_url = sklm_cert_url
                else: # replace certificate if existing certificate found
                    request_body['CertificateUri'] = {'@odata.id': sklm_cert_url}

                # Perform action to create or replace certificate
                response_url = REDFISH_OBJ.post(target_url, body=request_body)
                if response_url.status not in [200, 201, 202, 204]:
                    error_message = utils.get_extended_error(response_url)
                    result = {'ret': False, 'msg': "Url '%s' response Error code %s\nerror_message: %s" % (
                        target_url, response_url.status, error_message)}
                    return result

                result = {'ret': True,
                          'msg':"The SKLM %s certificate has been imported successfully." %(certtype)}
                return result

        # No CertificateService resource found
        result = {'ret': False, 'msg': 'CertificateService is not supported'}
        return result

    except Exception as e:
        result = {'ret': False, 'msg': 'exception msg %s' % e}
        return result
    finally:
        try:
            REDFISH_OBJ.logout()
        except:
            pass


def read_cert_file_pem(cert):
    try:
        fhandle = open(cert, 'r')
        filecontent = fhandle.read()
    except:
        filecontent = ''
    finally:
        fhandle.close()
    return filecontent if '-----BEGIN CERTIFICATE-----' in filecontent else None


def add_helpmessage(parser):
    parser.add_argument('--certtype', type=str, required=True, choices=["client", "server"],
                         help='Specify the type of the certificate. Support:["client", "server"]')
    parser.add_argument('--certfile', type=str, required=True, help="An file that contains certificate in PEM format. Certificate should be SKLM server certificate or signed client certificate. Note that the signed client certificate being imported must have been created from the Certificate Signing Request most recently created.")
 

def add_parameter():
    """Add parameter"""
    parameter_info = {}
    argget = utils.create_common_parameter_list()
    add_helpmessage(argget)
    args = argget.parse_args()
    parameter_info = utils.parse_parameter(args)
    parameter_info["certtype"] = args.certtype
    parameter_info["certfile"] = args.certfile
    return parameter_info


if __name__ == '__main__':
    # Get parameters from config.ini or command line
    parameter_info = add_parameter()
    ip = parameter_info['ip']
    login_account = parameter_info["user"]
    login_password = parameter_info["passwd"]
    certtype = parameter_info["certtype"]
    certfile = parameter_info["certfile"]

    # Import SKLM client or server certificate and check result
    result = lenovo_sklm_certificate_import(ip, login_account, login_password, certtype, certfile)
    if result['ret'] is True:
        del result['ret']
        sys.stdout.write(json.dumps(result['msg'], sort_keys=True, indent=2))
    else:
        sys.stderr.write(result['msg'] + '\n')

