#!/usr/bin/env python
# -*- coding: utf-8 -*-

import shutil
import sys
import math
import datetime
import argparse
import tempfile
import os
import json
import stat
import fnmatch
from git import Repo
from urlparse import urlparse

BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
HEX_CHARS = "1234567890abcdefABCDEF"

file_filter_patterns = []


def pathfilter(path):
    for pat in file_filter_patterns:
        if ("/" in pat) or ("\\" in pat):
            if fnmatch.fnmatch(path, pat):
                return None
        else:
            if fnmatch.fnmatch(os.path.basename(path), pat):
                return None
    return path


def main():
    # TODO : Add support for ignore files (.gitignore) in case of normal directory
    parser = argparse.ArgumentParser(description='Find secrets hidden in the depths of git.')
    parser.add_argument('--json', dest="output_json", action="store_true", help="Output in JSON")
    parser.add_argument('--gitignore', dest="gitignore", action="store_true", help="Ignore files in .gitignore file")
    parser.add_argument('--fileignore', dest="fileignore", help="Custom ignore files path")
    parser.add_argument('--start_date', dest="start_date", type=valid_date, help="Oldest date to consider in commit analysis. Format : YYYY-MM-DD")
    parser.add_argument('--end_date', dest="end_date", type=valid_date, help="Newest date to consider in commit analysis. Format : YYYY-MM-DD")
    parser.add_argument('source_location', type=str, help='Local path or Git URL for secret searching')

    args = parser.parse_args()
    url = urlparse(args.source_location)

    if not url.scheme:
        find_strings_in_dir(args.source_location, args.output_json, args.gitignore, args.fileignore)
    else:
        output = find_strings(args.source_location, args.output_json, args.gitignore, args.fileignore, args.start_date, args.end_date)
        project_path = output["project_path"]
        shutil.rmtree(project_path, onerror=del_rw)


def load_ignore_list(ignoreFile=""):
    if ignoreFile != "" and ignoreFile is not None:
        try:
            with open(ignoreFile, 'r') as f:
                for line in f:
                    if not (line[0] == "#"):
                        file_filter_patterns.append(line.rstrip())
        except Exception:
            pass


def valid_date(s):
    try:
        datetime.datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


def del_rw(action, name, exc):
    os.chmod(name, stat.S_IWRITE)
    os.remove(name)


def shannon_entropy(data, iterator):
    """
    Borrowed from http://blog.dkbza.org/2007/05/scanning-data-for-entropy-anomalies.html
    """
    if not data:
        return 0
    entropy = 0
    for x in iterator:
        p_x = float(data.count(x))/len(data)
        if p_x > 0:
            entropy += - p_x*math.log(p_x, 2)
    return entropy


def get_strings_of_set(word, char_set, threshold=20):
    count = 0
    letters = ""
    strings = []
    for char in word:
        if char in char_set:
            letters += char
            count += 1
        else:
            if count > threshold:
                strings.append(letters)
            letters = ""
            count = 0
    if count > threshold:
        strings.append(letters)
    return strings


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def clone_git_repo(git_url):
    project_path = tempfile.mkdtemp()
    Repo.clone_from(git_url, project_path)
    return project_path


def print_results(printJson, output, commit_time, branch_name, prev_commit, printableDiff, filename):
    if printJson:
        print(json.dumps(output, sort_keys=True, indent=4))
    else:
        if sys.version_info >= (3, 0):
            fileStr = "{}File: {}{}".format(bcolors.OKGREEN, filename, bcolors.ENDC)
            print(fileStr)
            dateStr = "{}Date: {}{}".format(bcolors.OKGREEN, commit_time, bcolors.ENDC)
            print(dateStr)
            branchStr = "{}Branch: {}{}".format(bcolors.OKGREEN, branch_name, bcolors.ENDC)
            print(branchStr)
            commitStrId = "{}Commit id: {}{}".format(bcolors.OKGREEN, prev_commit.name_rev, bcolors.ENDC)
            print(commitStrId)
            commitStr = "{}Commit: {}{}".format(bcolors.OKGREEN, prev_commit.message, bcolors.ENDC)
            print(commitStr)
            print(printableDiff)
        else:
            fileStr = "{}File: {}{}".format(bcolors.OKGREEN, filename, bcolors.ENDC)
            print(fileStr)
            dateStr = "{}Date: {}{}".format(bcolors.OKGREEN, commit_time, bcolors.ENDC)
            print(dateStr)
            branchStr = "{}Branch: {}{}".format(bcolors.OKGREEN, branch_name.encode('utf-8'), bcolors.ENDC)
            print(branchStr)
            commitStrId = "{}Commit id: {}{}".format(bcolors.OKGREEN, prev_commit.hexsha, bcolors.ENDC)
            print(commitStrId)
            commitStr = "{}Commit message: {}{}".format(bcolors.OKGREEN, prev_commit.message.encode('utf-8'), bcolors.ENDC)
            print(commitStr)
            print(printableDiff.encode('utf-8'))


# Serch an actual directory
def find_strings_in_dir(directory, printJson=False, gitIgnore=False, fileIgnore=""):
    res = {}
    stripped_dir = directory.rstrip('/')

    if gitIgnore:
        load_ignore_list(stripped_dir+'/.gitignore')
    if fileIgnore != "" and fileIgnore is not None:
        load_ignore_list(fileIgnore)

    for root, subdirs, files in os.walk(stripped_dir):
        files = [f for f in files if not f == '.gitignore' and pathfilter(f)]
        subdirs[:] = [d for d in subdirs if not d[0] == '.']
        for f in files:
            full_path = os.path.join(root, f)
            # Chop the directory from the left.
            display_path = full_path[len(stripped_dir) + 1:]

            text = open(full_path, 'r').read()
            flagged_strings = find_strings_for_text(text, display_path)
            res.update(flagged_strings)

    if printJson:
        print(json.dumps(res, sort_keys=True, indent=4))
    else:
        for title in res.keys():
            print(title + '\t' + res[title])


def find_strings_for_text(text, title, printableDiff=None):
    lines = text.split("\n")

    stringsFound = {}
    for idx, line in enumerate(lines):
        for word in line.split():
            base64_strings = get_strings_of_set(word, BASE64_CHARS)
            hex_strings = get_strings_of_set(word, HEX_CHARS)
            for string in base64_strings:
                b64Entropy = shannon_entropy(string, BASE64_CHARS)
                if b64Entropy > 4.5:
                    stringsFound[title + ':' + str(idx)] = string
                    if printableDiff:
                        printableDiff = printableDiff.replace(string, bcolors.WARNING + string + bcolors.ENDC)
                        stringsFound['printableDiff'] = printableDiff

            for string in hex_strings:
                hexEntropy = shannon_entropy(string, HEX_CHARS)
                if hexEntropy > 3:
                    stringsFound[title + ':' + str(idx)] = string
                    if printableDiff:
                        printableDiff = printableDiff.replace(string, bcolors.WARNING + string + bcolors.ENDC)
                        stringsFound['printableDiff'] = printableDiff

    return stringsFound


# Search Through a Git directory (either from Git URL like https://github.com/user/project.git or from file:///home/user/directory)
def find_strings(git_url, printJson=False, gitIgnore=False, fileIgnore="", startDate="", endDate=""):
    output = {"entropicDiffs": []}
    project_path = clone_git_repo(git_url)
    repo = Repo(project_path)
    already_searched = set()

    if gitIgnore:
        load_ignore_list(repo.git_dir+'/../.gitignore')

    if fileIgnore != "" and fileIgnore is not None:
        load_ignore_list(fileIgnore)

    for remote_branch in repo.remotes.origin.fetch():
        branch_name = remote_branch.name.split('/')[1]
        try:
            repo.git.checkout(remote_branch, b=branch_name)
        except Exception:
            pass

        prev_commit = None
        for curr_commit in repo.iter_commits():
            if not prev_commit:
                pass
            else:
                # avoid searching the same diffs
                hashes = str(prev_commit) + str(curr_commit)
                if hashes in already_searched:
                    prev_commit = curr_commit
                    continue
                already_searched.add(hashes)

                diff = prev_commit.diff(curr_commit, create_patch=True)
                for blob in diff:
                    # print i.a_blob.data_stream.read()
                    if blob.a_path:
                        if not pathfilter(blob.a_path):
                            continue

                    printableDiff = blob.diff.decode('utf-8', errors='replace')
                    if printableDiff.startswith("Binary files"):
                        continue

                    diff_text = blob.diff.decode('utf-8', errors='replace')
                    stringsFound = find_strings_for_text(diff_text, str(curr_commit), printableDiff)

                    if 'printableDiff' in stringsFound.keys():
                        printableDiff = stringsFound['printableDiff']

                    if len(stringsFound) > 0:
                        stringsFoundValues = stringsFound.values()
                        commit_time = datetime.datetime.fromtimestamp(prev_commit.committed_date).strftime('%Y-%m-%d %H:%M:%S')

                        # If we have older commits than starting date, stop the analysis
                        if startDate != "" and startDate is not None:
                            if datetime.datetime.fromtimestamp(prev_commit.committed_date) < datetime.datetime.strptime(startDate, "%Y-%m-%d"):
                                # print "Date limitation reached ("+startDate+"), stopping analysis"
                                output["project_path"] = project_path
                                return output

                        # If we have older commits than starting date, stop the analysis
                        if endDate != "" and endDate is not None:
                            if datetime.datetime.fromtimestamp(prev_commit.committed_date) > datetime.datetime.strptime(endDate, "%Y-%m-%d"):
                                # print prev_commit.committed_date
                                # print "Commit too recent (max is "+endDate+"), ignoring analysis"
                                continue

                        entropicDiff = {}
                        entropicDiff['date'] = commit_time
                        entropicDiff['branch'] = branch_name
                        entropicDiff['commit'] = prev_commit.message
                        entropicDiff['commit_id'] = prev_commit.hexsha
                        entropicDiff['diff'] = blob.diff.decode('utf-8', errors='replace')
                        entropicDiff['stringsFound'] = stringsFoundValues
                        output["entropicDiffs"].append(entropicDiff)

                        print_results(printJson, output, commit_time, branch_name, prev_commit, printableDiff, str(blob.a_path))
            prev_commit = curr_commit
    output["project_path"] = project_path
    return output


if __name__ == "__main__":
    main()
