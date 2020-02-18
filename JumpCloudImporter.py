# Copyright 2020 JumpCloud
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""See docstring for JumpCloudImporter class"""
from __future__ import absolute_import
from __future__ import print_function
import sys
# sys.path.append('/Users/jworkman/Documents/GitHub/autopkg/Code/autopkglib')
import os
# import sys
# sys.path.append('/usr/local/lib/python3.7/site-packages/jcapiv1')
# sys.path.append('/usr/local/lib/python3.7/site-packages/jcapiv2')
import datetime
import jcapiv1
import jcapiv2
import getpass
# import autopkglib3
from jcapiv2.rest import ApiException
from jcapiv1.rest import ApiException as ApiExceptionV1
from autopkglib import Processor, ProcessorError
# from autopkglib3 import Processor, ProcessorError
# used for testing
# from shutil import copy

import logging as log
import boto3
from botocore.exceptions import ClientError

__all__ = ["JumpCloudImporter"]
__version__ = "0.1.1"

# global vars #TODO: move all these into the class below
# TODO: consider just having the API key here as opposed to ~/Library/Preferences/com.github.autopkg.plist
CONTENT_TYPE = "application/json"
ACCEPT = "application/json"
CONFIGURATION = jcapiv2.Configuration()
CONFIGURATIONv1 = jcapiv1.Configuration()

# missingUpdate is an array to hold systems missing the app updates from
# the app currently being queried.
missingUpdate = []


# Global Variables #
# Name of System Group
sysGrpName = ""
# ID of System Group
sysGrpID = ""
# Name of Command
cmdName = ""
# ID of Command
cmdId = ""
# Download link for the cmd
cmdUrl = ""


class JumpCloudImporter(Processor):
    """This processor provides JumpCloud admins with a set of basic functions
    to query their systems for apps and build groups based on app requirements.

    Without input the processor will query all system insight enabled systems
    for the AutoPkg provided application name. If that system does not have the
    requested app, this processor will add that system to a group titled:
    AutoPkg-AppName-AppVersion.

    Taken with input, this processor can create custom group names and custom
    deployment types: SELF, AUTO or UPDATE.

    Deployment Type Descriptions:
    SELF:
    Self deployment runs will create the JumpCloud command and process the
    application specified in the recipe. The default group will be built and
    systems insights enabled systems that do not have that application will be
    added to that group. Admins can manually specify other groups or systems.

    AUTO:
    Auto deployment runs will create the JumpCloud command and a System Group using
    System Insights. JumpCloud systems are queried using system insights, systems
    that do not have the AutoPkg software title or have the software title with a
    previous version are added to this system group.

    System added to Group when:
    Does not have software title
    Software title is less than AutoPkg version

    Use Case:
    Mass deployment of a software title

    UPDATE:
    Update deployment runs will create the command containing a link to the
    package. Update deployments will also query system insight enabled
    systems and scope only those systems that match the following condition:
    System has application and the installed application is not equal to the
    latest version from AutoPkg.

    System added to Group when:
    Software title is less than AutoPkg version

    Use Case:
    Updating systems who have a specific software title installed

    Workflows:
    TODO: Nothing is specified
    """
    description = __doc__
    input_variables = {
        "JC_API": {
            "required": True,
            "description":
                "Password of api user, optionally set as a key in "
                "the com.github.autopkg preference file.",
        },
        "JC_SYSGROUP": {
            "required": False,
            "description": "If provided in recipe, the processor will build a smart "
            "group and assign systems without that application and version to the new group",
            "default": "default"
        },
        "pkg_path": {
            "required": False,
            "description":
                "Path to a pkg or dmg to import - provided by "
                "previous pkg recipe/processor.",
            "default": "",
        },
        "version": {
            "required": False,
            "description":
                "Version number of software to import - usually provided "
                "by previous pkg recipe/processor, but if not, defaults to "
                "'0.0.0.0'. ",
            "default": "0.0.0.0",
        },
        "JC_USER": {
            "required": False,
            "description": "JumpCloud user to who is designated to run command"
            "root user id in jumpcloud is: 000000000000000000000000",
            "default": "000000000000000000000000"
        },
        "JC_TYPE": {
            "required": False,
            "description": "type of deployment jumpcloud will process "
            "this field only be one of three values listed below: "
            "self, auto or update"
            "self - no scoping processed, just uses the commands API"
            "auto - system insights required, searches the database for "
            "systems and the specific app versions requested and builds "
            "groups based on that data"
            "update - deploy latest version of app to systems who already "
            "have that app installed.",
            "default": "self"
        },
        "JC_DIST": {
            "required": False,
            "description": "dist point for uploading compiled packages"
            "TODO: set this as a var in ~/Lib/prefs/com.github.autopkg.plist"
            "If dist = AWS"

            "if dist = SMB"

            "if dist = NULL",
            "default": None
        },
        "JC_DIY": {
            "required": False,
            "description": "dict for aws bucket"
        }


    }
    output_variables = {
        "module_file_path": {
            "description": "Outputs this module's file path."
        }
    }

    # init method or constructor
    # def __init__(self, env=None, infile=None, outfile=None):
    #     """Sets attributes here."""
    #     super(JumpCloudImporter, self).__init__(env, infile, outfile)
    #     self.jumpcloud = None
    #     self.groups_user_list = None
    #     self.groups = None
    #     # self.JC_SYSGROUP = None
    #     self.pkg_path = None
    #     self.globalCmdName = None
    #     self.version = None
    #     self.appName = self.env['NAME']
    #     self.JC_DIST = self.env['JC_DIST']
    #     # self.SystemGroupsApi = None
    #     # self.UserGroupsApi = None

    def connect_jc_online(self):
        """the connect_jc_online function is used once to set up the configuration 
        of the API key to the jcapi version 1 and 2
        """
        # Set up the configuration object with your API key for authorization
        # JC_API is stored in ~/Library/Preferences/com.github.autopkg.plist
        # set by running:
        # defaults write ~/Library/Preferences/com.github.autopkg.plist JC_API your_api_key
        kwargs = {
            'api': self.env['JC_API']
        }

        # Key Assignment #
        # From plist
        API_KEY = self.env['JC_API']
        # Interactive
        # key = getpass.getpass("JumpCloud API Key: ", stream=None)
        # API_KEY = key

        # TODO: change var name to configv2
        CONFIGURATION.api_key['x-api-key'] = API_KEY
        # TODO: delete this below?
        self.jumpcloud = jcapiv2.UserGroupsApi(
            jcapiv2.ApiClient(CONFIGURATION))

        # API_KEY = self.env['JC_API']
        CONFIGURATIONv1.api_key['x-api-key'] = API_KEY

    def get_si_systems(self):
        """This function compares the systems inventory with the v1 api, saves those
        systems to a list called inventory. 
        
        Systems with system insights are then queried, if a system insights inventory
        system is an Apple device and in the computer inventory it's returned
        """
        # system inventory
        inventory = []
        SI_SYSTEMS = jcapiv2.SystemInsightsApi(jcapiv2.ApiClient(CONFIGURATION))
        V1_SYSTEMS = jcapiv1.SystemsApi(jcapiv1.ApiClient(CONFIGURATIONv1))
        V1_api_response = V1_SYSTEMS.systems_list(CONTENT_TYPE, ACCEPT)
        # pprint(V1_api_response)
        for i in V1_api_response.results:
            inventory.append(i._id)
        # print("INVENTORY: " + str(inventory))
        try:
            skip = 0

            allSystems = []
            systems = SI_SYSTEMS.systeminsights_list_system_info(CONTENT_TYPE, ACCEPT, limit=100, skip=skip)
            # skip += 10
            # print(systems)

            for i in systems:
                # if system id is in the system inventory
                # sys insights can store items outside the inventory
                if i.system_id in inventory:
                    # filter by Apple Devices
                    if i._hardware_vendor == 'Apple Inc.':
                        # create list of systems which have system insights data
                        allSystems.append(i.system_id)
            # return list of systems wish si data
            return allSystems
        except ApiException as err:
            print("Exception when calling SystemInsightsApi->systeminsights_list_system_info %s\n" % err)

    def get_si_apps_id(self, sysID, app):
        """This function gathers information about each system insights 
        system, using AutoPkg as an input source this function queries
        systems based on the app recipe name.
        
        Systems with the app are recorded to compare versions. 

        Systems without the application are added to the sytem group
        specifid in the recipe. 
        """
        SI_APPS = jcapiv2.SystemInsightsApi(
            jcapiv2.ApiClient(CONFIGURATION))
        try:
            # skip int used to iterate through sys insights apps
            searchInt = 0
            # array to hold the results of what I actually want
            appArry = []
            # continue to search while the app list does not return zero
            condition = True
            # short dynamic var for function below
            name = sysID[:6]
            # Search by system
            search = ['system_id:eq:%s' % sysID]

            while condition:
                apps = SI_APPS.systeminsights_list_apps(CONTENT_TYPE, ACCEPT, skip=searchInt, limit=100, filter=search)
                for i in apps:
                    if "/Applications/" in i.path:
                        appArry.append(i.bundle_name)
                        # print(i.bundle_name + " " + i.bundle_short_version)
                        if app == i.bundle_name:
                            name = {
                                "system": sysID,
                                "application": i.bundle_name,
                                "app_version": i.bundle_short_version
                            }
                            # add the system to the missing update array
                            missingUpdate.append(name)
                # search next 100 apps/ max limit of the jumpcloud API
                searchInt += 100
                if len(apps) == 0:
                    condition = False
            if app in appArry:
                print(app + " found on system : " + sysID)
            else:
                print(app + " not found on system: " + sysID)
                # print(self.env.get("JC_SYSGROUP"))
                self.add_system_to_group(sysID, self.sysGrpID)
        except ApiException as err:
            print("Exception when calling SystemInsightsApi->systeminsights_list_apps: %s\n" % err)

    def query_app_versions(self):
        """This function compares system app versions against the autopkg
        app version

        This function adds or removes systems from a system group. If 
        systems have the latest version of an App, they are removed from
        the AutoPkg sytem group.

        If systems do not have the latest version of the app they are added
        to the AutoPkg system group.
        """
        # sis = self.get_si_systems()
        for i in missingUpdate:
            if (i["app_version"] != self.env.get("version") or self.env.get("version") == "0.0.0.0"):
                print("system:" + i["system"] + " " + i["application"] + " needs updating")
                print(i["app_version"] + " requires updating to... " +
                      self.env.get("version"))
                self.add_system_to_group(i["system"], self.sysGrpID)
                # self.add_system_to_group(i["system"], self.env["SYS_GROUP"])
            if (i["app_version"] == self.env.get("version")):
                print("system:" + i["system"] + " " +
                      i["application"] + " does not require updating")
                print(i["app_version"] + " already on latest version... " +
                      self.env.get("version"))
                self.remove_system_from_group(i["system"], self.sysGrpID)

    def add_system_to_group(self, system, group):
        """Adds system to a group"""
        # TODO: consider moving the "is system in this group?" to own func
        JC_SYS_GROUP = jcapiv2.SystemGroupMembersMembershipApi(jcapiv2.ApiClient(CONFIGURATION))
        composite = []
        group_id = group
        body = jcapiv2.SystemGroupMembersReq(
            id=system, op="add", type="system")
        try:
            getstuff = JC_SYS_GROUP.graph_system_group_membership(
                group_id, CONTENT_TYPE, ACCEPT)
            for i in getstuff:
                composite.append(i.id)
            if system not in composite:
                print("adding " + system + " to " + group)
                JC_SYS_GROUP.graph_system_group_members_post(group_id, CONTENT_TYPE, ACCEPT, body=body)
            else: 
                print("system " + system + " already in group " + group)
        except ApiException as err:
            print(
                "Exception when calling SystemGroupMembersApi->graph_system_group_members_post:" % err)

    def remove_system_from_group(self, system, group):
        """Remove system from a group"""
        # TODO: consider moving the "is system in this group?" to own func
        JC_SYS_GROUP = jcapiv2.SystemGroupMembersMembershipApi(jcapiv2.ApiClient(CONFIGURATION))
        composite = []
        group_id = group
        body = jcapiv2.SystemGroupMembersReq(
            id=system, op="remove", type="system")
        try:
            getstuff = JC_SYS_GROUP.graph_system_group_membership(
                group_id, CONTENT_TYPE, ACCEPT)
            for i in getstuff:
                composite.append(i.id)
            if system in composite:
                print("removing " + system + " from " + group)
                JC_SYS_GROUP.graph_system_group_members_post(group_id, CONTENT_TYPE, ACCEPT, body=body)
            else:
                print("system " + system + " not in group " + group)
        except ApiException as err:
            print(
                "Exception when calling SystemGroupMembersApi->graph_system_group_members_post:" % err)
    
    def set_global_vars(self):
        """
        This command defines the global variables which are used by the processor to create and build
        commands and system groups.

        Currently additional checks are needed:
        TODO:
        * Group Name (sysGrpName)
        """
        self.env["globalCmdName"] = "%s" % "AutoPkg-" + self.env['NAME'] + "-" + self.env.get("version")
        self.cmdName = "%s" % "AutoPkg-" + self.env['NAME'] + "-" + self.env.get("version")

    def check_command(self, name):
        """Check if command exists by comparing autopkg names

        This fucntion takes input from the JC_SYSGROUP parameter 
        and checks a commandexists with the same name on JumpCloud.

        if the command does not exist, return true indicating that the
        group should be build.

        if the command exists return false, the command does not need 
        to be created
        """
        JC_CMD = jcapiv1.CommandsApi(jcapiv1.ApiClient(CONFIGURATIONv1))
        filter = "name:eq:%s" % name
        try:
            # Get a Command File
            api_response = JC_CMD.commands_list(CONTENT_TYPE, ACCEPT, filter=filter)
            # print(api_response)
            if api_response.total_count == 0:
                print("Command does not exist")
                return True
            else:
                print("Command: " + name + " already exists")
                return False

        except ApiExceptionV1 as err:
            print("Exception when calling CommandsApi->commands_post: %s\n" % err)

    def get_command_id(self, name):
        """This function returns the ID of a matching command
        name in the JumpCloud console
        """
        JC_CMD = jcapiv1.CommandsApi(jcapiv1.ApiClient(CONFIGURATIONv1))
        filter = "name:eq:%s" % name
        try:
            # Get a Command File
            api_response = JC_CMD.commands_list(CONTENT_TYPE, ACCEPT, filter=filter)
            # result = api_response.get()
            # print("Get Python Testing")
            # print(api_response)
            if api_response.total_count > 1:
                print("FAILURE - too many commands with the same name")
            else:
                # print("Command ID:" + api_response._results[0].id)
                self.cmdId = api_response._results[0].id
                return api_response._results[0].id

        except ApiExceptionV1 as err:
            print("Exception when calling CommandsApi->commands_post: %s\n" % err)
    
    def set_command(self, nameVar):
        """Create a JumpCloud command to be edited by the edit_command 
        function. 
        
        This fuction sets the name of the command to nameVar
        """
        JC_CMD = jcapiv1.CommandsApi(jcapiv1.ApiClient(CONFIGURATIONv1))
        # line indentations are deliberate to account for bash
        query = (
            '''
#!/bin/bash
''')
        usr = self.env["JC_USER"]
        body = jcapiv1.Command(
            name="%s" % nameVar,
            command="%s" % query,
            command_type="mac",
            user="%s" % usr,
            timeout="900",
        )
        try:
            # Get a Command File
            api_response = JC_CMD.commands_post(CONTENT_TYPE, ACCEPT, body=body, async_req=True)
            result = api_response.get()
            # print(dir(result))
            print("Command created: " + nameVar)
            # print(result)
        except ApiExceptionV1 as err:
            print("Exception when calling CommandsApi->commands_post: %s\n" % err)

    def edit_command(self, file_name, url, id):
        """Populates the command created by set_command
        
        This function adds:
        the systemGroup to the command (to run the 
        command, once per system)

        the url of the AWS object into the command
        """
        # trim the filename
        # print(file_name + "  " + self.sysGrpID + "  " + id)
        object_name = os.path.basename(file_name)
        JC_CMD = jcapiv1.CommandsApi(jcapiv1.ApiClient(CONFIGURATIONv1))
        # line indentations are deliberate to account for bash
        query = (
'''
#!/bin/bash
# Populate systemGroupID variable before running the command
# this variable should correspond to the AutoPkg group from JCImporter

systemGroupID="{0}"

#---------------------Imported from JC Importer-----------------------
curl --silent --output /tmp/{1} "{2}"
installer -pkg /tmp/{1} -target /
#--------------------Do not modify below this line--------------------

# Parse the systemKey from the conf file.
conf="$(cat /opt/jc/jcagent.conf)"
regex='\"systemKey\":\"[a-zA-Z0-9]{{24}}\"'

if [[ $conf =~ $regex ]]; then
	systemKey="${{BASH_REMATCH[@]}}"
fi

regex='[a-zA-Z0-9]{{24}}'
if [[ $systemKey =~ $regex ]]; then
	systemID="${{BASH_REMATCH[@]}}"
fi

# Get the current time.
now=$(date -u "+%a, %d %h %Y %H:%M:%S GMT")

# create the string to sign from the request-line and the date
signstr="POST /api/v2/systemgroups/${{systemGroupID}}/members HTTP/1.1\ndate: ${{now}}"

# create the signature
signature=$(printf "$signstr" | openssl dgst -sha256 -sign /opt/jc/client.key | openssl enc -e -a | tr -d '\\n')

curl -s \\
	-X 'POST' \\
	-H 'Content-Type: application/json' \\
	-H 'Accept: application/json' \\
	-H "Date: ${{now}}" \\
	-H "Authorization: Signature keyId=\"system/${{systemID}}\",headers=\"request-line date\",algorithm=\"rsa-sha256\",signature=\"${{signature}}\"" \\
	-d '{{"op": "remove","type": "system","id": "'${{systemID}}'"}}' \\
	"https://console.jumpcloud.com/api/v2/systemgroups/${{systemGroupID}}/members"

echo "JumpCloud system: ${{systemID}} removed from system group: ${{systemGroupID}}"
exit 0
''')
        query = query.format(self.sysGrpID, object_name, url)
        usr = self.env["JC_USER"]
        # files uploaded in list[str] format where str is an ID of a jumpcloud
        # file variable for selecting the AutoPkg package path
        #TODO: switch to self.cmdName
        cmdName = self.env["globalCmdName"]

        # use when uploading to a distribution point
        body = jcapiv1.Command(
            name="%s" % cmdName,
            command="%s" % query,
            command_type="mac",
            user="%s" % usr,
            timeout="900",
        )
        try:
            # update the command
            api_response = JC_CMD.commands_put(id, CONTENT_TYPE, ACCEPT, body=body)
            # for debugging:
            # print(api_response)
        except ApiExceptionV1 as err:
            print("Exception when calling CommandsApi->commands_post: %s\n" % err)

    def associate_command_with_group_post(self, command_id, group_id):
        ASSOC_CMD = jcapiv2.SystemGroupAssociationsApi(jcapiv2.ApiClient(CONFIGURATION))
        print("Associating command: " + command_id + " to system group: " + group_id)
        # group_id = '5dc1a63645886d6c72b87116'
        # cdm_id = self.get_command_id(self.env["globalCmdName"])
        body = jcapiv2.SystemGroupGraphManagementReq(
            id=command_id, op="add", type="command")
        try:
            ASSOC_CMD.graph_system_group_associations_post(group_id, CONTENT_TYPE, ACCEPT, body=body)
        except ApiException as e:
            print("Exception when calling SystemGroupAssociationsApi->graph_system_group_associations_post: %s\n" % e)

    def associate_command_with_group_list(self, command_id, group_id):
        """
        Get the associations of a particular system group, return true if 
        the command_id is associated with the group_id. Use this function 
        to determine if the system group needs to be associated with 
        newly built commands.
        """
        ASSOC_CMD = jcapiv2.SystemGroupAssociationsApi(jcapiv2.ApiClient(CONFIGURATION))
        targets = ['command']
        try:
            api_response = ASSOC_CMD.graph_system_group_associations_list(group_id, CONTENT_TYPE, CONTENT_TYPE, targets)
            # print(api_response)
            i = 0
            # should be zero for an array containing one command result
            # print("response length is: " + str(len(api_response)))
            while i < len(api_response):
                print("group association exists at index: " + str(i) + " : " + api_response[i]._to.id)
                if api_response[i]._to.id == command_id:
                    print("commandID: " + command_id + " matches " + api_response[i]._to.id + " association found at index " + str(i))
                    return True
                i += 1
            # TODO: just call associate_command_with_group_list if this is false
            return False
        except ApiException as e:
            print("Exception when calling SystemGroupAssociationsApi->graph_system_group_associations_list: %s\n" % e)

    def define_group(self, inputGroup):
        """Checks for name validity"""
        try:
            if inputGroup == "default":
                print("no group specified, defaulting to default naming structure")
                self.sysGrpName = str(
                    self.env['NAME'] + "-AutoPkg-" + self.env.get("version"))
                print(self.sysGrpName)
                return self.sysGrpName
            else:

                # print("Listing: " + self.env([JC_SYSGROUP]))
                # self.sysGrpName = self.env.get("JC_SYSGROUP")
                self.sysGrpName = inputGroup
                return self.sysGrpName
        except NameError:
            print("this is not a valid group")

    def get_group(self, inputGroup):
        """Search JumpCloud for existing group"""
        JC_GROUPS = jcapiv2.SystemGroupsApi(jcapiv2.ApiClient(CONFIGURATION))
        try:
            search = ['name:eq:%s' % inputGroup]
            lGroup = JC_GROUPS.groups_system_list(
                CONTENT_TYPE, ACCEPT, filter=search)

            for i in lGroup:
                if (i.name == inputGroup):
                    self.sysGrpID = i.id
                    print("THE GROUP ID IS: " + self.sysGrpID)
                    return True
                else:
                    return False

        except ApiException as err:
            print("Exception when calling SystemGroupsApi->groups_system_list: %s\n" % err)

    def set_group(self, inputGroup):
        """This function creates a new sysetm group"""
        # build the template group object based off user input or default values
        JC_GROUPS = jcapiv2.SystemGroupsApi(jcapiv2.ApiClient(CONFIGURATION))
        try:
            body = jcapiv2.SystemGroupData(inputGroup)
            nGroup = JC_GROUPS.groups_system_post(
                CONTENT_TYPE, ACCEPT, body=body)

        except ApiException as err:
            print("Exception when calling SystemGroupsApi->SystemGroupData: %s\n" % err)

    def check_pkg(self):
        """Check the status of the package. This function is used to verify
        that the package path is not null.

        it currently validates taht the JC_DIST variable is not null but this 
        needs work before it's actually useful. 
        """
        pkg_path = self.env["pkg_path"]
        jc_dist = self.env["JC_DIST"]
        if pkg_path is not None and jc_dist is not None:
            # print(pkg_path + " package exists")
            # print(jc_dist + " is real")
            # with open(pkg_path, "rb") as f:
            #     copy(f, jc_dist)
            return True
        else:
            return False
        # return true or false

    def upload_fake_file(self, file_name, bucket, object_name=None):
        """Formatting and copying file

        :param file_name: File to upload
        :param bucket: Bucket to upload to
        :param object_name: S3 object name. If not specified then file_name
        is used
        :return: True if file was uploaded, else False

        Unless modified, the object_name will exist in the root directory
        of the bucket.
        """
        # using os.path.basename, get the package
        # file_name is to locate the package
        # object_name is the bucket object item
        object_name = os.path.basename(file_name)
        if object_name is None:
            object_name = file_name

        # fake upload the file
        print("filename is: " + file_name)
        print("object name is: " + object_name)
        print("check this out: " + os.path.basename(file_name))
        jc_dist = self.env["JC_DIST"]
        if file_name is not None and jc_dist is not None:
            print(file_name + " package exists")
            print(jc_dist + " is real")
            #FIXME: tupel index out of range
            print(file_name + " " + self.cmdId )
            # self.edit_command(file_name, "bogus", self.cmdId)
            self.edit_command(file_name, "something", self.cmdId)
            # with open(pkg_path, "rb") as f:
            #     copy(f, jc_dist)

    def upload_file(self, file_name, bucket, object_name=None):
        """Upload a file to an S3 bucket

        :param file_name: File to upload
        :param bucket: Bucket to upload to
        :param object_name: S3 object name. If not specified, file_name is used
        :return: True if file was uploaded, else False
        """
        # If S3 object_name was not specified, use file_name
        if object_name is None:
            object_name = os.path.basename(file_name)
            # object_name = file_name

        # Upload the file
        s3_client = boto3.client('s3')
        try:
            response = s3_client.upload_file(file_name, bucket, object_name)
            location = boto3.client('s3').get_bucket_location(
                Bucket=bucket)['LocationConstraint']
            url = "https://s3-%s.amazonaws.com/%s/%s" % (location, bucket, object_name)
            self.cmdUrl = url
            # print(url)
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def main(self):
        try:
            print("=================================================")
            module_file_path = os.path.abspath(__file__)
            # TODO: verbose instructions here
            # print(sys.version)

            # Connect to API v1 and 2 endpoints
            self.connect_jc_online()

            # Define Group Name based on AutoPkg software (default)
            # Define Group Name based on user input if necessary
            self.define_group(self.env["JC_SYSGROUP"])

            # Check if group defined above exists
            if self.get_group(self.sysGrpName):
                print(" System group exists, no need to create new group")
            else:
                print(" System group does not exist, creating group:")
                self.set_group(self.sysGrpName)
                # verify the group was created and get the new ID
                self.get_group(self.sysGrpName)

            if self.env["JC_TYPE"] == "auto":
                # QUERY SYSTEMS
                print("============== BEGIN SYSTEM QUERY ===============")
                for i in self.get_si_systems():
                    self.get_si_apps_id(i, self.env['NAME'])
                print("=============== END SYSTEM QUERY ================")
                print("=================================================")
                # print(self.env.get("version"))

                # QUERY APPS ON SYSTEMS
                print("============== BEGIN VERSION QUERY ==============")
                self.query_app_versions()
                print("=============== END VERSION QUERY ===============")
                print("=================================================")

            # Set naming conventions for command and package name
            self.set_global_vars()
            # Check if the package path exists

            #TODO: use in upload logic testing 
            # commented out for testing
            # if self.check_pkg():
            #     print("true condition")
            # else:
            #     print("fail condition")

            print("============== BEGIN COMMAND CHECK ==============")
            if self.env["JC_DIST"] == "AWS":
                # if command does not exist do the following
                if self.check_command(self.cmdName):
                    # create command for the first time
                    self.set_command(self.cmdName)
                    # return id of command
                    self.get_command_id(self.cmdName)
                    # with returned value of command upload package
                    ## testing function ##
                    # self.upload_fake_file(self.env["pkg_path"], "jcautopkg")
                    ## end testing function ##
                    ## AWS functions to run with packages ##
                    self.upload_file(self.env["pkg_path"], "jcautopkg")
                    self.edit_command(self.env["pkg_path"], self.cmdUrl, self.cmdId)
                    ## END AWS functions ##
                else:
                    # command exists just return id
                    self.get_command_id(self.cmdName)
            print("=============== END COMMAND CHECK ===============")
            print("=================================================")

            print("========== BEGIN COMMAND ASSOCIATIONS ===========")
            # ### testing
            # Associate command with system group
            if not self.associate_command_with_group_list(self.get_command_id(self.env["globalCmdName"]), self.sysGrpID):
                self.associate_command_with_group_post(self.get_command_id(self.env["globalCmdName"]), self.sysGrpID)
            else:
                print("Command Already associated with the group")

            print("=========== END COMMAND ASSOCIATIONS ============")
            print("=================================================")

            self.output("The input variable data '%s' was given to this "
                        "Processor." % self.env['NAME'])
            self.output("The input variable data '%s' was given to this "
                        "Processor." % self.env["JC_DIST"])
            # print(self.appName)

            ### testing
            self.output(
                "This shared processor is located at %s" % module_file_path)
            self.env["module_file_path"] = module_file_path
        except Exception as err:
            # handle unexpected errors here
            raise ProcessorError(err)


if __name__ == "__main__":
    PROCESSOR = JumpCloudImporter()
    PROCESSOR.execute_shell()