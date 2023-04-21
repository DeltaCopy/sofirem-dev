# =================================================================
# =                 Author: Cameron Percival                      =
# =================================================================

import os
import sys
import shutil
import psutil
import time
import datetime
from datetime import datetime, timedelta
import subprocess
import threading  # noqa
import gi
import requests
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool

# import configparser
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa
from queue import Queue  # Multithreading the caching
from threading import Thread
from ProgressBarWindow import ProgressBarWindow
from sofirem import launchtime
from Package import Package

# =====================================================
#               Base Directory
# =====================================================

base_dir = os.path.dirname(os.path.realpath(__file__))

# =====================================================
#               Global Variables
# =====================================================
sudo_username = os.getlogin()
home = "/home/" + str(sudo_username)
path_dir_cache = base_dir + "/cache/"
packages = []
debug = False

# =====================================================
#               Create log file
# =====================================================

log_dir = "/var/log/sofirem/"
sof_log_dir = "/var/log/sofirem/software/"
act_log_dir = "/var/log/sofirem/actions/"


def create_packages_log():
    now = datetime.now().strftime("%H:%M:%S")
    print("[INFO] " + now + " Creating a log file in /var/log/sofirem/software")
    destination = sof_log_dir + "software-log-" + launchtime
    command = "sudo pacman -Q > " + destination
    subprocess.call(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    create_actions_log(
        launchtime,
        "[INFO] %s Creating a log file in /var/log/sofirem/software " % now + "\n",
    )
    # GLib.idle_add(
    #     show_in_app_notification, "is already installed - nothing to do", "test"
    # )


def create_actions_log(launchtime, message):
    if not os.path.exists(act_log_dir + launchtime):
        try:
            with open(act_log_dir + launchtime, "x", encoding="utf8") as f:
                f.close
        except Exception as error:
            print(error)

    if os.path.exists(act_log_dir + launchtime):
        try:
            with open(act_log_dir + launchtime, "a", encoding="utf-8") as f:
                f.write(message)
                f.close()
        except Exception as error:
            print(error)


# =====================================================
#               GLOBAL FUNCTIONS
# =====================================================


def _get_position(lists, value):
    data = [string for string in lists if value in string]
    position = lists.index(data[0])
    return position


def isfileStale(filepath, staleDays, staleHours, staleMinutes):
    # first, lets obtain the datetime of the day that we determine data to be "stale"
    now = datetime.now()
    # For the purposes of this, we are assuming that one would have the app open longer than 5 minutes if installing.
    staleDateTime = now - timedelta(
        days=staleDays, hours=staleHours, minutes=staleMinutes
    )
    # Check to see if the file path is in existence.
    if os.path.exists(filepath):
        # if the file exists, when was it made?
        fileCreated = datetime.fromtimestamp(os.path.getctime(filepath))
        # file is older than the time delta identified above
        if fileCreated < staleDateTime:
            return True
    return False


# =====================================================
#               PERMISSIONS
# =====================================================


def permissions(dst):
    try:
        groups = subprocess.run(
            ["sh", "-c", "id " + sudo_username],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        for x in groups.stdout.decode().split(" "):
            if "gid" in x:
                g = x.split("(")[1]
                group = g.replace(")", "").strip()
        subprocess.call(["chown", "-R", sudo_username + ":" + group, dst], shell=False)

    except Exception as e:
        print(e)


# =====================================================
#               PACMAN SYNC PACKAGE DB
# =====================================================
def sync():
    try:
        pacman_lock_file = "/var/lib/pacman/db.lck"
        sync_str = ["pacman", "-Sy"]
        now = datetime.now().strftime("%H:%M:%S")
        print("[INFO] %s Synchronising package databases" % now)
        create_actions_log(
            launchtime,
            "[INFO] %s Synchronising package databases " % now + "\n",
        )

        # Pacman will not work if there is a lock file
        if os.path.exists(pacman_lock_file):
            print("[ERROR] Pacman lock file found")
            print("[ERROR] Sync failed")

            msg_dialog = Functions.message_dialog(
                            self,
                            "pacman -Sy",
                            "Pacman database synchronisation failed",
                            "Pacman lock file found inside %s" % pacman_lock_file,
                            Gtk.MessageType.ERROR,
            )

            msg_dialog.run()
            msg_dialog.hide()
            sys.exit(1)
        else:

            process_sync = subprocess.run(
                sync_str,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
            )

        return process_sync.returncode
    except Exception as e:
        print("Exception in sync(): %s" % e)


# =====================================================
#               APP INSTALLATION
# =====================================================
def install(self,pkg_queue,signal,switch):

    pkg = pkg_queue.get()
    install_state={}
    install_state[pkg] = None

    try:
        if waitForPacmanLockFile() == False and \
            checkPackageInstalled(pkg) == False and \
            signal == "install":

            path = base_dir + "/cache/installed.lst"

            inst_str = ["pacman", "-S", pkg, "--needed", "--noconfirm"]

            now = datetime.now().strftime("%H:%M:%S")
            print("[INFO] %s Installing package %s " % (now, pkg))
            create_actions_log(
                launchtime, "[INFO] " + now + " Installing package " + pkg + "\n"
            )

            process_pkg_inst = subprocess.Popen(
                inst_str,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            out, err = process_pkg_inst.communicate(timeout=60)

            if process_pkg_inst.returncode == 0:
                get_current_installed()
                install_state[pkg] = "INSTALLED"

                print(
                    "[INFO] %s Package install : %s status = completed" %
                        (datetime.now().strftime("%H:%M:%S"),pkg)
                )
                print(
                    "---------------------------------------------------------------------------"
                )

                GLib.idle_add(
                    show_in_app_notification, 
                    self,
                    "Package: %s installed" % pkg,
                )


            else:
                # deactivate switch widget, install failed
                switch.set_active(False)
                get_current_installed()
                print("[ERROR] %s Package install : %s status = failed" %
                        (datetime.now().strftime("%H:%M:%S"),pkg)
                )
                if out:
                    out = out.decode("utf-8")
                    install_state[pkg] = out
                    print(install_state[pkg])
                print(
                    "---------------------------------------------------------------------------"
                )

                GLib.idle_add(
                    show_in_app_notification, 
                    self,
                    "[ERROR] Failed to install package: %s" % pkg,
                )

                raise SystemError("Pacman failed to install package = %s" % pkg)


        elif(checkPackageInstalled(pkg)):
            install_state[pkg] = "INSTALLED"
            print("[INFO] %s Package %s is already installed" %
                    (datetime.now().strftime("%H:%M:%S"),pkg)
            )

    except SystemError as s:
        print("SystemError in install(): %s" % s)
    except Exception as e:
        print("Exception in install(): %s" % e)
    finally:
        '''
            Now check install_state for any packages which failed to install
        '''
            # display dependencies notification to user here


        #print("error" in install_state[pkg].splitlines())
        if install_state[pkg] != "INSTALLED":
            msg_dialog = message_dialog(
                self,
                "Error installing package",
                "Failed to install package: %s" % pkg,
                str(install_state[pkg]),
                Gtk.MessageType.ERROR,
            )
            msg_dialog.run()
            msg_dialog.hide()
            

        if install_state[pkg] == "INSTALLED":
            switch.set_active(True)
        else:
            switch.set_active(False)

        pkg_queue.task_done()



# =====================================================
#               APP UNINSTALLATION
# =====================================================
def uninstall(self,pkg_queue,signal,switch):

    pkg = pkg_queue.get()
    uninstall_state={}
    uninstall_state[pkg] = None

    try:
        if waitForPacmanLockFile() == False and \
            checkPackageInstalled(pkg) and \
            signal == "uninstall":

                path = base_dir + "/cache/installed.lst"
                uninst_str = ["pacman", "-Rs", pkg, "--noconfirm"]

                now = datetime.now().strftime("%H:%M:%S")
                print("[INFO] %s Removing package : %s" % (now, pkg))
                create_actions_log(
                    launchtime, "[INFO] " + now + " Removing package " + pkg + "\n"
                )

                process_pkg_rem = subprocess.Popen(
                    uninst_str,
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )

                out, err = process_pkg_rem.communicate(timeout=60)

                if process_pkg_rem.returncode == 0:
                    get_current_installed()
                    uninstall_state[pkg] = "REMOVED"
                    print(
                        "[INFO] %s Package removal : %s status = completed" %
                            (datetime.now().strftime("%H:%M:%S"),pkg)
                        )
                    print(
                        "---------------------------------------------------------------------------"
                    )

                    GLib.idle_add(
                        show_in_app_notification, 
                        self,
                        "Package: %s removed" % pkg,
                    )

                else:
                    # reactivate switch widget, the package has not been removed
                    switch.set_active(True)
                    get_current_installed()
                    print(
                        "[ERROR] %s Package removal : %s status = failed" %
                            (datetime.now().strftime("%H:%M:%S"),pkg)
                    )
                    if out:
                        out = out.decode("utf-8")
                        uninstall_state[pkg] = out.splitlines()
                        print(out)
                    print(
                        "---------------------------------------------------------------------------"
                    )

                    GLib.idle_add(
                    show_in_app_notification, 
                    self,
                    "[ERROR] Failed to remove package: %s" % pkg,
                )

                    raise SystemError("Pacman failed to remove package = %s" % pkg)

        elif(checkPackageInstalled(pkg) == False):
            uninstall_state[pkg] = "REMOVED"
            print("[INFO] %s Package %s is already uninstalled" %
                    (datetime.now().strftime("%H:%M:%S"),pkg)
            )

    except SystemError as s:
        print("SystemError in uninstall(): %s" % s)

    except Exception as e:
        print("Exception in uninstall(): %s" % e)

    finally:
        '''
            Now check uninstall_state for any packages which failed to uninstall
        '''
            # display dependencies notification to user here

        if uninstall_state[pkg] != "REMOVED":

            msg_dialog = message_dialog(
                self,
                "Error removing package",
                "Failed to remove package: %s" % pkg,
                str(uninstall_state[pkg]),
                Gtk.MessageType.ERROR,
            )

            msg_dialog.run()
            msg_dialog.hide()



        if uninstall_state[pkg] == "REMOVED":
            switch.set_active(False)
        else:
            switch.set_active(True)

        pkg_queue.task_done()

# =====================================================
#               SEARCH INDEXING
# =====================================================

# store a list of package metadata into memory for fast retrieval
def storePackages():
    path = base_dir + "/yaml/"
    yaml_files = []
    packages = []

    category_dict = {}

    try:

        # get a list of yaml files
        for file in os.listdir(path):
            if file.endswith(".yaml"):
                yaml_files.append(file)

        if len(yaml_files) > 0:
            for yaml_file in yaml_files:
                cat_desc = ""
                package_name = ""
                package_cat = ""

                category_name = yaml_file[11:-5].strip().capitalize()

                # read contents of each yaml file

                with open(path+yaml_file, "r") as yaml:
                    content = yaml.readlines()
                for line in content:
                    if line.startswith("  packages:"):
                        continue
                    elif line.startswith("  description: "):
                        # Set the label text for the description line
                        subcat_desc = (
                            line.strip("  description: ").strip().strip('"').strip("\n").strip()
                        )
                    elif line.startswith("- name:"):
                        # category
                        subcat_name = line.strip("- name: ").strip().strip('"').strip("\n").strip()
                    elif line.startswith("    - "):
                        # add the package to the packages list

                        package_name = line.strip("    - ").strip()
                        # get the package description
                        package_desc = obtain_pkg_description(package_name)

                        package = Package(
                                package_name,
                                package_desc,
                                category_name,
                                subcat_name,
                                subcat_desc,
                        )

                        packages.append(package)
                

        # filter the results so that each category holds a list of package

        category_name = None
        packages_cat = []
        for pkg in packages:
            if category_name == pkg.category:
                packages_cat.append(pkg)
                category_dict[category_name] = packages_cat
            elif category_name == None:
                packages_cat.append(pkg)
                category_dict[pkg.category] = packages_cat
            else:
                # reset packages, new category
                packages_cat = []

                packages_cat.append(pkg)

                category_dict[pkg.category] = packages_cat

            category_name = pkg.category

        '''
        for key in category_dict.keys():
            print("Category = %s" % key)
            pkg_list = category_dict[key]

            for pkg in pkg_list:
                print(pkg.name)
                #print(pkg.category)

            
            print("++++++++++++++++++++++++++++++")
        '''

        sorted_dict = None

        sorted_dict = dict(sorted(category_dict.items()))


        return sorted_dict
    except Exception as e:
        print("Exception in storePackages() : %s" % e)



# =====================================================
#               CREATE MESSAGE DIALOG
# =====================================================

# show the dependencies error here which is stopping the install/uninstall pkg process
def message_dialog(self, title, first_msg, secondary_msg, msg_type):

    msg_dialog = Gtk.MessageDialog(
        self,
        flags=0,
        message_type=msg_type,
        buttons=Gtk.ButtonsType.OK,
        text=first_msg,
    )

    msg_dialog.set_title(title)

    if len(secondary_msg) > 0:
        msg_dialog.format_secondary_markup(
            "<b> %s </b> " % secondary_msg
        )

    return msg_dialog

# =====================================================
#               APP QUERY
# =====================================================


def get_current_installed():
    path = base_dir + "/cache/installed.lst"
    # query_str = "pacman -Q > " + path
    query_str = ["pacman", "-Q"]
    # run the query - using Popen because it actually suits this use case a bit better.

    subprocess_query = subprocess.Popen(
        query_str, 
        shell=False, 
        stdout=subprocess.PIPE,
    )

    out, err = subprocess_query.communicate(timeout=60)

    # added validation on process result
    if subprocess_query.returncode == 0:
        file = open(path, "w")
        for line in out.decode("utf-8"):
            file.write(line)
        file.close()
    else:
        print(
            "[ERROR] %s Failed to run %s"
            % (datetime.now().strftime("%H:%M:%S"), query_str)
        )


def query_pkg(package):
    try:
        package = package.strip()
        path = base_dir + "/cache/installed.lst"

        if os.path.exists(path):
            if isfileStale(path, 0, 0, 30):
                get_current_installed()
        # file does NOT exist;
        else:
            get_current_installed()
        # then, open the resulting list in read mode
        with open(path, "r") as f:

            # first we need to strip the new line escape sequence to ensure we don't get incorrect outcome
            pkg = package.strip("\n")

            # If the pkg name appears in the list, then it is installed
            for line in f:
                installed = line.split(" ")
                # We only compare against the name of the package, NOT the version number.
                if pkg == installed[0]:
                    # file.close()
                    return True
            # We will only hit here, if the pkg does not match anything in the file.
            # file.close()
        return False
    except Exception as e:
        print("Exception in query_pkg(): %s " % e)


# =====================================================
#        PACKAGE DESCRIPTION CACHE AND SEARCH
# =====================================================


def cache(package, path_dir_cache):
    try:
        # first we need to strip the new line escape sequence to ensure we don't get incorrect outcome
        pkg = package.strip()
        # you can see all the errors here with the print command below
        if debug == True:
            print(pkg)
        # create the query
        query_str = ["pacman", "-Si", pkg, " --noconfirm"]

        # run the query - using Popen because it actually suits this use case a bit better.

        process = subprocess.Popen(
            query_str, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        out, err = process.communicate()

        # validate the process result
        if process.returncode == 0:
            if debug == True:
                print("Return code: equals 0 " + str(process.returncode))
            # out, err = process.communicate()

            output = out.decode("utf-8")

            if len(output) > 0:
                split = output.splitlines()

                # Currently the output of the pacman command above always puts the description on the 4th line.
                desc = str(split[3])
                # Ok, so this is a little fancy: there is formatting from the output which we wish to ignore (ends at 19th character)
                # and there is a remenant of it as the last character - usually a single or double quotation mark, which we also need to ignore
                description = desc[18:]
                # writing to a caching file with filename matching the package name
                filename = path_dir_cache + pkg

                file = open(filename, "w")
                file.write(description)
                file.close()

                return description
        # There are several packages that do not return a valid process return code
        # Cathing those manually via corrections folder
        if process.returncode != 0:
            if debug == True:
                print("Return code: " + str(process.returncode))
            exceptions = [
                "florence",
                "mintstick-bin",
                "arcolinux-conky-collection-plasma-git",
                "arcolinux-desktop-trasher-git",
                "arcolinux-pamac-all",
                "arcolinux-sddm-simplicity-git",
                "ttf-hack",
                "ttf-roboto-mono",
                "aisleriot",
                "mailspring",
                "linux-rt",
                "linux-rt-headers",
                "linux-rt-lts",
                "linux-rt-lts-headers",
                "arcolinux-sddm-simplicity-git",
                "kodi-x11",
                "kodi-addons",
                "sardi-icons",
            ]
            if pkg in exceptions:
                description = file_lookup(pkg, path_dir_cache + "corrections/")
                return description
        return "No Description Found"

    except Exception as e:
        print("Exception in cache(): %s " % e)


# Creating an over-load so that we can use the same function, with slightly different code to get the results we need
def cache_btn():
    # fraction = 1 / len(packages)
    # Non Multithreaded version.
    packages.sort()
    number = 1
    for pkg in packages:
        print(str(number) + "/" + str(len(packages)) + ": Caching " + pkg)
        cache(pkg, path_dir_cache)
        number = number + 1
        # progressbar.timeout_id = GLib.timeout_add(50, progressbar.update, fraction)

    print(
        "[INFO] Caching applications finished  " + datetime.now().strftime("%H:%M:%S")
    )

    # This will need to be coded to be running multiple processes eventually, since it will be manually invoked.
    # process the file list
    # for each file in the list, open the file
    # process the file ignoring what is not what we need
    # for each file line processed, we need to invoke the cache function that is not over-ridden.


def file_lookup(package, path):
    # first we need to strip the new line escape sequence to ensure we don't get incorrect outcome
    pkg = package.strip("\n")
    output = ""
    if os.path.exists(path + "corrections/" + pkg):
        filename = path + "corrections/" + pkg
    else:
        filename = path + pkg
    file = open(filename, "r")
    output = file.read()
    file.close()
    if len(output) > 0:
        return output
    return "No Description Found"


def obtain_pkg_description(package):
    # This is a pretty simple function now, decide how to get the information, then get it.
    # processing variables.
    output = ""
    path = base_dir + "/cache/"

    # First we need to determine whether to pull from cache or pacman.
    if os.path.exists(path + package.strip("\n")):
        output = file_lookup(package, path)

    # file doesn't exist, so create a blank copy
    else:
        output = cache(package, path)
    # Add the package in question to the global variable, in case recache is needed
    packages.append(package)
    return output


def restart_program():
    os.unlink("/tmp/sofirem.lock")
    python = sys.executable
    os.execl(python, python, *sys.argv)


# def check_github(yaml_files):
#     # This is the link to the location where the .yaml files are kept in the github
#     # Removing desktop wayland, desktop, drivers, nvidia, ...
#     path = base_dir + "/cache/"
#     link = "https://github.com/arcolinux/arcob-calamares-config-awesome/tree/master/calamares/modules/"
#     urls = []
#     fns = []
#     for file in yaml_files:
#         if isfileStale(path + file, 14, 0, 0):
#             fns.append(path + file)
#             urls.append(link + file)
#     if len(fns) > 0 & len(urls) > 0:
#         inputs = zip(urls, fns)
#         download_parallel(inputs)


# def download_url(args):
#     t0 = time.time()
#     url, fn = args[0], args[1]
#     try:
#         r = requests.get(url)
#         with open(fn, "wb") as f:
#             f.write(r.content)
#         return (url, time.time() - t0)
#     except Exception as e:
#         print("Exception in download_url():", e)


# def download_parallel(args):
#     cpus = cpu_count()
#     results = ThreadPool(cpus - 1).imap_unordered(download_url, args)
#     for result in results:
#         print("url:", result[0], "time (s):", result[1])


# =====================================================
#               CHECK RUNNING PROCESS
# =====================================================


def checkIfProcessRunning(processName):
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=["pid", "name", "create_time"])
            if processName == pinfo["pid"]:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False


# =====================================================
#               CHECK PACMAN LOCK FILE
# =====================================================


def waitForPacmanLockFile():
    timeout = 60
    start = int(time.time())

    while True:
        if os.path.exists("/var/lib/pacman/db.lck"):
            print("[INFO] %s Waiting for previous Pacman transaction to complete" %
                    datetime.now().strftime("%H:%M:%S")
            )

            time.sleep(5)

            elapsed = int(time.time()) + 5

            print("[INFO] %s Elapsed duration : %s" %
                    (datetime.now().strftime("%H:%M:%S"),(elapsed - start))
                )


            if (elapsed - start) >= timeout:
                print("[WARN] %s Waiting for previous Pacman transaction timed out after %ss" %
                    (datetime.now().strftime("%H:%M:%S"),timeout)
                )
                break
        else:
            return False


# =====================================================
#               CHECK PACKAGE INSTALLED
# =====================================================


def checkPackageInstalled(pkg):
    try:
        query_str = ["pacman", "-Q", pkg]

        process_query = subprocess.Popen(
            query_str,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        out, err = process_query.communicate(timeout=60)

        if process_query.returncode == 0:
            return True
        else:
            return False
    except Exception as e:
        print("Exception in checkPackageInstalled(): %s", e)


# =====================================================
#               MESSAGEBOX
# =====================================================


def messageBox(self, title, message):
    md2 = Gtk.MessageDialog(
        parent=self,
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    md2.format_secondary_markup(message)
    md2.run()
    md2.destroy()


# =====================================================
#               USER SEARCH
# =====================================================


def search(self, term):
    try:
        print("[INFO] %s Searching for: \"%s\"" % (
                datetime.now().strftime("%H:%M:%S"),
                term,
            )
        )

        pkg_matches = []

        category_dict = {}

        whitespace = False

        if term.strip():
            whitespace = True

        for pkg_list in self.packages.values():
            for pkg in pkg_list:
                if whitespace:
                    for te in term.split(" "):
                        if te in pkg.name \
                            or te in pkg.description:
                            # only unique name matches
                            if pkg not in pkg_matches:
                                pkg_matches.append(
                                    pkg,
                                )
                else:    
                    if term in pkg.name \
                        or term in pkg.description:
                            pkg_matches.append(
                                pkg,
                            )
        '''
        for p in pkg_matches:
            print(p.name)
        '''

        # filter the results so that each category holds a list of package

        category_name = None
        packages_cat = []
        for pkg_match in pkg_matches:
            if category_name == pkg_match.category:
                packages_cat.append(pkg_match)
                category_dict[category_name] = packages_cat
            elif category_name == None:
                packages_cat.append(pkg_match)
                category_dict[pkg_match.category] = packages_cat
            else:
                # reset packages, new category
                packages_cat = []

                packages_cat.append(pkg_match)

                category_dict[pkg_match.category] = packages_cat

            category_name = pkg_match.category

        if len(category_dict) == 0:
            self.search_queue.put(None)
            msg_dialog = message_dialog(
                self,
                "Find Package",
                "\"%s\" was not found in the available sources" % term,
                "Please try another search query",
                Gtk.MessageType.ERROR,
            )

            msg_dialog.run()
            msg_dialog.hide()

        # debug console output to display package info
        '''
        # print out number of results found from each category
        print("[DEBUG] %s Search results.." % datetime.now().strftime("%H:%M:%S"))

        for category in sorted(category_dict):
            category_res_len = len(category_dict[category])
            print("[DEBUG] %s %s = %s" %(
                        datetime.now().strftime("%H:%M:%S"),
                        category,
                        category_res_len,
                    )
            )
        '''

        # sort dictionary so the category names are displayed in alphabetical order
        sorted_dict = None

        if len(category_dict) > 0:
            sorted_dict = dict(sorted(category_dict.items()))
            self.search_queue.put(
                sorted_dict,
            )
        else:
            return

    except Exception as e:
        print("Exception in search(): %s", e)

# =====================================================
#               NOTIFICATIONS
# =====================================================

def show_in_app_notification(self, message):
    if self.timeout_id is not None:
        GLib.source_remove(self.timeout_id)
        self.timeout_id = None

    self.notification_label.set_markup(
        '<span foreground="white">' + message + "</span>"
    )
    self.notification_revealer.set_reveal_child(True)
    self.timeout_id = GLib.timeout_add(3000, timeOut, self)


def timeOut(self):
    close_in_app_notification(self)


def close_in_app_notification(self):
    self.notification_revealer.set_reveal_child(False)
    GLib.source_remove(self.timeout_id)
    self.timeout_id = None

#######ANYTHING UNDER THIS LINE IS CURRENTLY UNUSED!
