import base64
import copy
import json
import os
import re
import shutil
import threading
import time
import tkinter as tk
from datetime import date, datetime
from io import BytesIO
from math import ceil
from tkinter import font
from tkinter import ttk

import keyring
import pandas as pd
import pyperclip
import requests
from PIL import Image, ImageTk
from requests.auth import HTTPBasicAuth
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

session = requests.Session()
session.headers = {"User-Agent": "e6-Recommendation-System/1.0 (by DestroyingFilms on e621)"}

INTENTIONAL_DELAY = 1  # second. Needed to meet the requirements of the e621 API service

scrollable_area_color = '#2e2e2e'
overlays_color = '#444444'
buttons_color = '#ffaa00'
sidebar_color = '#3e3e3e'

today = date.today()


# Write modifications and new options to OS (API key) and local config.json file (everything else)
def write_to_config(conf):
    keyring.set_password('e6_rec_API', '', conf.get('profile', {}).get('API_key', ''))
    conff = copy.deepcopy(conf)
    conff['profile']['API_key'] = '[HIDDEN]'
    with open('config.json', 'w') as f:
        json.dump(conff, f, indent=4)


# Upon launch load configurations, at least, attempt to do so.
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
        if {'profile', 'options', 'advanced'}.issubset(config.keys()):
            config['profile']['login'] = str(config['profile'].get('login', ''))
            raw = keyring.get_password('e6_rec_API', '')
            if raw:
                if not config['profile']['login'].strip() or len(config['profile']['login'].strip())>100:
                    temp_API_key = ''
                    keyring.set_password('e6_rec_API', '', temp_API_key)
                else:
                    temp_API_key = raw
            else:
                temp_API_key = ''
            # Get all the values from the file, or get default ones, if something seems to be off.
            config['profile']['API_key'] = str(temp_API_key)[:100]
            config['options']['auto_load'] = bool(config['options'].get('auto_load', True))
            config['options']['logging'] = bool(config['options'].get('logging', True))
            config['options']['blacklist'] = config['options'].get('blacklist',
                                                                   ["young", "loli", "shota", "gore", "feces",
                                                                    "urine"]) if type(
                config['options'].get('blacklist', ["young", "loli", "shota", "gore", "feces", "urine"])) == list else [
                "young", "loli", "shota", "gore", "feces", "urine"]
            config['options']['blacklist'] = ('\n'.join(config['options']['blacklist'])[:10000]).split('\n')
            config['options']['min_score'] = int(config['options'].get('min_score', 0)) if str(
                config['options'].get('min_score', 0)).isnumeric() else 0
            if -999 <= config['options'][
                'min_score'] <= 999:  # If configuration in the file goes beyond a certain limit.
                pass
            else:
                config['options']['min_score'] = 0

            config['options']['default_rating'] = str(config['options'].get('default_rating', 's')) if config[
                                                                                                           'options'].get(
                'default_rating', 's') in ['s', 'q', 'e', 'a'] else 's'
            config['advanced']['threads'] = int(config['advanced'].get('threads', 5)) if str(
                config['advanced'].get('threads', 5)).isnumeric() else 5
            if 1 <= config['advanced']['threads'] <= 50:
                pass
            else:
                config['advanced']['threads'] = 5
            config['advanced']['posts_per_thread'] = int(config['advanced'].get('posts_per_thread', 10)) if str(
                config['advanced'].get('posts_per_thread', 10)).isnumeric() else 10
            if 1 <= config['advanced']['posts_per_thread'] <= 100:
                pass
            else:
                config['advanced']['posts_per_thread'] = 10
            config['advanced']['grading'] = str(config['advanced'].get('grading', 'max')) if config['advanced'].get(
                'grading', 'max') in ['max', 'avg'] else 'max'
# If it fails, then resort to a default configuration.
except:
    config = {
        'profile':
            {
                'login': '',
                'API_key': ''
            },
        'options':
            {
                'auto_load': True,
                'logging': True,
                'blacklist': ["young", "loli", "shota", "gore", "feces", "urine"],
                # This is a default blacklist, where the first three tags are always blacklisted no matter what.
                'min_score': 0,
                'default_rating': 's'
            },
        'advanced':
            {
                'threads': 5,
                'posts_per_thread': 10,
                'grading': 'max'
            }
    }
    write_to_config(config)


# Write debug info to log files
def write_to_log(msg, day_of_creation=str(date.today()), time_of_creation=datetime.now().strftime("%H-%M-%S")):
    if config['options']['logging']:
        if msg.count('\n') > 0:
            msgs = msg.split('\n')
            formated_msg = ''
            for msg in msgs:
                formated_msg += f'[{datetime.now().strftime("%H:%M:%S")}]: {str(msg)}\n'
            with open(f'data/logs/log-{day_of_creation}-{time_of_creation}.log', 'a') as f:
                f.write(formated_msg)
            with open(f'data/logs/latest.log', 'a') as f:
                f.write(formated_msg)
        else:
            formated_msg = f'[{datetime.now().strftime("%H:%M:%S")}]: {str(msg)}\n'
            with open(f'data/logs/log-{day_of_creation}-{time_of_creation}.log', 'a') as f:
                f.write(formated_msg)
            with open(f'data/logs/latest.log', 'a') as f:
                f.write(formated_msg)


try:
    all_files = sorted(
        [file for file in os.listdir('data/logs') if re.search('log-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}.log', file)])
    latest_log = int(re.search('\d+', all_files[-1]).group())
except (FileNotFoundError, IndexError):
    os.makedirs('data/logs', exist_ok=True)
    latest_log = -1
    all_files = []
with open(f'data/logs/latest.log', 'w') as f:
    f.write('')
config_for_log = copy.deepcopy(config)
config_for_log['profile']['API_key'] = '[HIDDEN]'
write_to_log(f'Program started!\nCurrent date: {today}\nCurrent config: {config_for_log}')

# Only 10 log files must exist in the /logs folder (excluding latest.log). So if there is more, attempt to remove very old ones.
for file in all_files:
    if len(all_files) < 10:
        break
    file_path = os.path.join('data/logs/', file)
    all_files.remove(file)
    try:
        if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)
    except Exception as e:
        write_to_log(f'Failed to delete %s. Reason: %s' % (file_path, e))


# Used to figure out if the preview image of the result was actually downloaded or not. If not (not base64) then use placeholder instead.
def is_base64(s):
    try:
        base64.b64decode(s, validate=True)
        return True
    except:
        return False


# Class for the whole GUI tk app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self.on_exit)  # Attemping to close the window
        self.current_state = 'confirmation'  # Shows what is the current state of the program and the results. VARIATIONS: 'confirmation' (shows first warning), 'initial' (an actual initial state), 'loading' (start was pressed), 'completed' (showing the results)
        self.data_state = 'start'  # Shows the state of "Start" process or recommendation system state. VARIATIONS: 'start' (creating missing folders), 'fav' (download favorite posts), 'lat' (download latest posts), 'rec' (starting recommendation service), 'error' (something went wrong during the process).
        self.data_response = [
            None]  # Contains the response for the questions from the "Start" process, such as "Do you want to re-download your favorite posts?". VARIATIONS: [None], [True], [False]
        self.loading_state = 'loading'  # Shows the state of loading first preview images. VARIATIONS: 'loading' (still loading or needs to be loaded, reloaded), 'complete' (already loaded)
        self.copy_state = 'nothing'  # Provides the state of copy overlay "Copied the link successfully". VARIATIONS: 'nothing' (not shown), 'showing' (is being shown)
        self.check_state = False  # If the program checked the correctness of user's profile before starting the recommendation process yet. VARIATIONS: False (haven't checked yet), True (checked)
        self.exit_state = 'nothing'  # The same story as copy_state but not with the exit overlay. VARIATIONS: 'nothing' (not shown), 'showing' (is being shown)
        self.ability_to_exit = False  # Block attempts to close the program if something related to threads is happening right now. VARIATIONS: False (user cannot normally exit the program, an overlay will be shown), True (user can exit the program safely)
        self.cancel_loading = False  # If the cancel command was sent by the user during the recommendation phase. VARIATIONS: False (no cancel request), True (user cancelled the process)
        self.title("e6 Recommendation")
        self.geometry("900x600")
        self.resizable(False, False)
        self.tk_images = []  # A list that contains PhotoImages of previews for the recommendations
        self.tk_images_data = []  # A list that contains information for those previews, such as id, url, per (percentage or grade), ext (file extension of the original post)
        # self.loading_frame = None
        self.how_many_images_to_download = 30  # Parameter that tells the algorithm how many top recommendations should have a preview image downloaded to a local system.
        self.more_images = 0  # Multiplier to load more images after the previous ones. This works in the range - (self.how_many_images_to_download * self.more_images, self.how_many_images_to_download * (self.more_images + 1))
        self.load_images_limit = False  # This shows if the limit of posts were hit. If the program attempts to load more images, while there is not enough left in the results, then this parameter will be activated.
        self.columns = 4  # Amount of columns of results
        self.page_number = 0  # Current help section page
        self.help_loaded = False  # Check if the images that help uses were already loaded
        self.help_pages = [{
            'text': 'Hello and welcome to this recommendation system!\n\nAs you might have already guessed, this system works with e621 posts.',
            'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.5, 'additional_img': None}, {
            'text': 'I will not waste your time, and will get right into it.\n\nBehind and above this overlay is the main window where previews of recommendations will be provided.',
            'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.8, 'additional_img': None}, {
            'text': {'condition': 'self.current_state',
                     'true': 'The window itself will look something like this.\n\nBut of course top images will have proper previews and IDs.',
                     'false': "I see you already have your recommendations.\n\nThen I guess there is not need to show you how it looks like."},
            'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.8,
            'additional_img': {'img': 'data/help/preview_of_previews.png', 'x': 0, 'y': 0}}, {
            'text': {'condition': 'self.current_state',
                     'true': 'This right here is a post ID, which you can click on and copy the url to that same post.',
                     'false': "But, what you might not have known is the fact that IDs are clickable, which copies the link to the original post to your clipboard.", },
            'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.3,
            'additional_img': {'img': 'data/help/preview_of_previews_ID.png', 'x': 0, 'y': 0}}, {
            'text': {'condition': 'self.current_state',
                     'true': 'While this is a confidence percentage.\nThis is how confident the algorithm is about recommending you this post.',
                     'false': "Oh, and this is a confidence percentage.\nThere is no guarantee that you will absolutely love the recommendations.\nYou can adjust the settings to change your recommendations"},
            'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.4,
            'additional_img': {'img': 'data/help/preview_of_previews_per.png', 'x': 0, 'y': 0}},

            {'text': {'condition': 'self.current_state',
                      'true': 'You can get the results of the recommendation after starting the process using this "Start" button.',
                      'false': 'After changing the options, you can run the process once again using the same "Start" button'},
             'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.2,
             'additional_img': {'img': 'data/help/preview_of_previews_start.png', 'x': 0, 'y': 0}},

            {
                'text': "When clicking the start button a pop-up will appear with loading status of recommendations, starting with downloading your favorite posts page-by-page.",
                'width': 400, 'height': 200, 'rel_x': 0.49, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_start_fav_download.png', 'x': 0, 'y': 0}},

            {
                'text': "But before that, if you downloaded your favorite posts already, then you can choose to re-download them or not.",
                'width': 400, 'height': 200, 'rel_x': 0.49, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_start_fav.png', 'x': 0, 'y': 0}},

            {
                'text': "Oh yeah, by the way. The recommendation works with local copies of posts data, so it needs to be downloaded using e621 API.",
                'width': 400, 'height': 200, 'rel_x': 0.49, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_start_fav.png', 'x': 0, 'y': 0}},

            {
                'text': "After that the same story goes with latest posts. If you haven't downloaded them already, then this pop-up will be skipped.",
                'width': 400, 'height': 200, 'rel_x': 0.49, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_start_lat.png', 'x': 0, 'y': 0}},

            {
                'text': "When everything needed was downloaded, the recommendation begins, and most of the time, it won't take long.",
                'width': 400, 'height': 200, 'rel_x': 0.49, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_start_rec.png', 'x': 0, 'y': 0}},

            {
                'text': f"But what would take long (>45 seconds) is the saving of the results.\nAs the algorithm begins to download preview images of top recommendations.",
                'width': 400, 'height': 200, 'rel_x': 0.49, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_start_rec.png', 'x': 0, 'y': 0}},

            {'text': 'Then ones again, back to the main screen, with new recommendations displayed right here.',
             'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.7,
             'additional_img': {'img': 'data/help/preview_of_previews.png', 'x': 0, 'y': 0}},

            {'text': "So now, let's talk about the options.", 'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.7,
             'additional_img': {'img': 'data/help/preview_of_previews_options.png', 'x': 0, 'y': 0}},

            {'text': "There are multiple settings that you can adjust to your liking.", 'width': 400, 'height': 200,
             'rel_x': 0.65, 'rel_y': 0.7,
             'additional_img': {'img': 'data/help/preview_of_previews_options_just.png', 'x': 0, 'y': 0}},

            {
                'text': 'The first one is "Profile", where you can change the profile to use during recommendations.\nYou will need to provide username for it.',
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_profile.png', 'x': 0, 'y': 0}},

            {
                'text': 'API key is optional. But if you have hidden your favorites, then you will have to provide API key for the program to be able to access them.',
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_profile.png', 'x': 0, 'y': 0}},

            {
                'text': "Next is " + '"' + "Blacklist" + '"' + ", where you can provide a list of tags you DON'T want to be recommended.",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_blacklist.png', 'x': 0, 'y': 0}},

            {
                'text': "Blacklist by default only has six tags, that you can see above.\nThree of them are in the grey-ish zone and they cannot be removed or changed. They will always be blacklisted.",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_blacklist.png', 'x': 0, 'y': 0}},

            {
                'text': "It will work during a downloading process of your favorite and latest posts.\nThe posts that contain blacklisted tag will not be downloaded.",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_blacklist.png', 'x': 0, 'y': 0}},

            {
                'text': "And remember, complex tags cannot be used in this blacklist, only one tag per line. And a limit of 10k characters exist.",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_blacklist.png', 'x': 0, 'y': 0}},

            {'text': "Now, this is a minimum score threshold, which can range from -999 to 999.", 'width': 400,
             'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
             'additional_img': {'img': 'data/help/preview_of_previews_options_min_score.png', 'x': 0, 'y': 0}},

            {
                'text': "If a latest post has a score of more than minimum score threshold, then it will used during recommendation process.\n(Default: 0)",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_min_score.png', 'x': 0, 'y': 0}},

            {
                'text': "Default post rating is quite simple, as it is a parameter that tells the algorithm to use only those posts that have the same rating as the one right here.",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_default_rating.png', 'x': 0, 'y': 0}},

            {
                'text': 'Options are: Safe, Questionable, Explicit and Any.\n"Any" tells the algorithm to use any post, no matter their rating.\n(Default: Safe)',
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_options_default_rating.png', 'x': 0, 'y': 0}},

            {
                'text': 'Auto load is the checkmark that makes the program automatically load previews of your recommendations upon loading. (Default: ON)',
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.3,
                'additional_img': {'img': 'data/help/preview_of_previews_options_auto_load.png', 'x': 0, 'y': 0}},

            {'text': 'If you have it turned off...', 'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.3,
             'additional_img': {'img': 'data/help/preview_of_previews_options_auto_load.png', 'x': 0, 'y': 0}},

            {'text': '... then this is where the "Load" button will help you see your results.', 'width': 400,
             'height': 200, 'rel_x': 0.5, 'rel_y': 0.5,
             'additional_img': {'img': 'data/help/preview_of_previews_load.png', 'x': 0, 'y': 0}},

            {
                'text': "What might be interesting is the option to turn on/off logging.\nThis is needed for debugging issues that might occur in the program. (DEFAULT: ON)",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.3,
                'additional_img': {'img': 'data/help/preview_of_previews_options_logging.png', 'x': 0, 'y': 0}},

            {
                'text': "This will create log files in the data/logs/ folder.\nAPI key is hidden and not shown in the logs.",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.3,
                'additional_img': {'img': 'data/help/preview_of_previews_options_logging.png', 'x': 0, 'y': 0}},

            {'text': 'The folder (data/logs/) can only contain max of 10 files, and one additional "latest.log".',
             'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.3,
             'additional_img': {'img': 'data/help/preview_of_previews_options_logging.png', 'x': 0, 'y': 0}},

            {
                'text': "Now the last options are advanced, that are a bit more complex than regular ones. So that's why I will provide you with detailed instruction on them.",
                'width': 400, 'height': 200, 'rel_x': 0.65, 'rel_y': 0.3,
                'additional_img': {'img': 'data/help/preview_of_previews_options_advanced.png', 'x': 0, 'y': 0}},

            {
                'text': "As you can see, I've already tried to give some description for each option.\nHowever, they might not be clear for some.",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced.png', 'x': 0, 'y': 0}},

            {
                'text': "The first option is the number of threads to use.\nThe algorithm works by using threads to achieve parallel grading system of all the posts.",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced_threads.png', 'x': 0, 'y': 0}},

            {
                'text': "If the algorithm were to use a single thread to grade each latest post, then it would take a lot of time to grade all of them.\nThat's why parallel system is much more needed here.",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced_threads.png', 'x': 0, 'y': 0}},

            {
                'text': "The number of threads that you can use is a range from 1 to 50 inclusively.\nTypically, the more threads you have, the faster the grading is, but CPU will have to create those threads, so more usage.",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced_threads.png', 'x': 0, 'y': 0}},

            {
                'text': "The algorithm divides all the latest posts to groups, so that it won't overflow memory with all the data and their grades at once.\nThis is where the options of posts per thread comes in.",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced_posts_per.png', 'x': 0, 'y': 0}},

            {
                'text': "This is how many of the latest posts will be used in one thread to compare them with your favorite ones.",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced_posts_per.png', 'x': 0, 'y': 0}},

            {
                'text': "The range is from 1 to 100 inclusively.\nI've noticed that this is the primary option to increase the speed of the algorithm if you choose a high number. But it will also increase CPU and RAM usage.",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced_posts_per.png', 'x': 0, 'y': 0}},

            {
                'text': "Now the last advanced option is the grading method, with two choices: MAX and AVG (The one greyed out is the currently selected method).",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.3,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced_grade.png', 'x': 0, 'y': 0}},

            {'text': "This needs some additional explanation so I will do just that.", 'width': 400, 'height': 200,
             'rel_x': 0.5, 'rel_y': 0.7,
             'additional_img': {'img': 'data/help/preview_of_previews_nothing.png', 'x': 0, 'y': 0}},

            {'text': "Let's say you have your favorite posts...", 'width': 400, 'height': 200, 'rel_x': 0.5,
             'rel_y': 0.7, 'additional_img': {'img': 'data/help/preview_of_previews_demo_fav.png', 'x': 0, 'y': 0}},

            {'text': "... and the latest posts.\nFor the simplicity sake, let's say you only have one latest post.",
             'width': 400, 'height': 200, 'rel_x': 0.7, 'rel_y': 0.7,
             'additional_img': {'img': 'data/help/preview_of_previews_demo_lat.png', 'x': 0, 'y': 0}},

            {
                'text': "Now the recommendation system will compare how similar each latest post with each of your favorites, and output the results using percentage.",
                'width': 400, 'height': 200, 'rel_x': 0.7, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_demo_lat.png', 'x': 0, 'y': 0}},

            {
                'text': "We will say that you have these kind of results for that one latest post. Where it is quite similar with your second favorite post, but not as similar with the third one.",
                'width': 400, 'height': 200, 'rel_x': 0.7, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_demo_grades.png', 'x': 0, 'y': 0}},

            {
                'text': "But now how do we give a definitive grade for this latest post, if the results are varying with each of your favorites? This is where different grading methods provide options.",
                'width': 400, 'height': 200, 'rel_x': 0.7, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_demo_grades.png', 'x': 0, 'y': 0}},

            {
                'text': 'The "MAX" method will get the maximum similarity and count it as a grade to recommend you this post. For this example, it will have a grade of 78.3%',
                'width': 400, 'height': 200, 'rel_x': 0.7, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_demo_grades_max.png', 'x': 0, 'y': 0}},

            {
                'text': 'While the "AVG" method will get all the results and calculate the average result, which is a grade for this post. With those results, it will have a grade of 44.907%',
                'width': 400, 'height': 200, 'rel_x': 0.7, 'rel_y': 0.7,
                'additional_img': {'img': 'data/help/preview_of_previews_demo_grades_avg.png', 'x': 0, 'y': 0}},

            {
                'text': 'A final grade is quite different depending on what grading method was chosen. But both of these have their own pros and cons.',
                'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.8,
                'additional_img': {'img': 'data/help/preview_of_previews_demo_grades_max_avg.png', 'x': 0, 'y': 0}},

            {
                'text': '"MAX" might be too keen on specific tags.\nIf you have favorited one post with some particular tags, then the system will recommend posts with these tags, even when all the other favorites are different.',
                'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.8,
                'additional_img': {'img': 'data/help/preview_of_previews_demo_grades_max_avg.png', 'x': 0, 'y': 0}},

            {
                'text': '"AVG" will only give a high grade to a post that is similar to almost all of your favorites.\nThis becomes a problem when you have quite varying favorites.',
                'width': 400, 'height': 200, 'rel_x': 0.5, 'rel_y': 0.8,
                'additional_img': {'img': 'data/help/preview_of_previews_demo_grades_max_avg.png', 'x': 0, 'y': 0}},

            {
                'text': "So, I give you the option to choose one method or the other, based on your personal preference.\nMight be worth to try both of them out.",
                'width': 400, 'height': 200, 'rel_x': 0.275, 'rel_y': 0.3,
                'additional_img': {'img': 'data/help/preview_of_previews_advanced_grade.png', 'x': 0, 'y': 0}},

            {'text': "That's all. Hope this help was useful for you.\nHappy finding your new favorites!", 'width': 400,
             'height': 200, 'rel_x': 0.5, 'rel_y': 0.5, 'additional_img': None},

        ]

        self.configure(bg=scrollable_area_color)
        style = ttk.Style(self)
        style.configure("TButton", font=("Segoe UI", 12), padding=6, relief="flat")
        style.map("TButton", background=[("active", buttons_color)],
                  foreground=[("active", "black"), ("disabled", "#969696")])
        style.configure('Horizontal.TScale', background=overlays_color)
        style.map('Horizontal.TScale', background=[("active", overlays_color)])
        style.configure('TCheckbutton', background=overlays_color)
        style.map('TCheckbutton', background=[("active", overlays_color)])

        self.sidebar = tk.Frame(self, width=150, bg=sidebar_color)
        self.sidebar.pack(side="right", fill="y")

        self.main_area = tk.Frame(self, bg=scrollable_area_color)
        self.main_area.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(self.main_area, bg=scrollable_area_color, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.main_area, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=scrollable_area_color)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        ttk.Button(self.sidebar, text="Start", command=self.start_process_thread).pack(pady=10, fill="x", padx=10)
        ttk.Button(self.sidebar, text="Load",
                   command=lambda: (write_to_log('"Load" pressed.'), self.load_process())).pack(pady=10, fill="x",
                                                                                                padx=10)
        ttk.Button(self.sidebar, text="Options",
                   command=lambda: (write_to_log('"Options" pressed.'), self.disable_sidebar(),
                                    self.show_options_overlay())).pack(pady=10, fill="x", padx=10)
        ttk.Button(self.sidebar, text="Help", command=lambda: (write_to_log('"Help" pressed.'), self.disable_sidebar(),
                                                               self.show_help_overlay())).pack(pady=10, fill="x",
                                                                                               padx=10)
        ttk.Button(self.sidebar, text="Exit", command=lambda: (write_to_log('"Exit" pressed.'), self.on_exit())).pack(
            pady=10, fill="x", padx=10)

        write_to_log('Init successfull.')

        self.first_launch_state()

    # A mandatory check
    def first_launch_state(self):
        write_to_log('First launch state.')
        self.disable_sidebar()
        self.ability_to_exit = True
        self.show_confirm_overlay('Are you over 18?',
                                  'The content seen here is not appropriate for young individuals.\nThe application itself is configured with\ndefault blacklist and a "safe" post rating.',
                                  lambda: (self.enable_sidebar(), self.confirm_frame.destroy(),
                                           self.set_initial_state()), lambda: (write_to_log('END'), self.destroy()))

    # Help section.
    # Overlay that is shown when pressing on "Help" button.
    def show_help_overlay(self):
        self.ability_to_exit = False
        # Attemping to show the image if the current page requires one
        if self.help_pages[self.page_number]['additional_img']:
            if self.help_pages[self.page_number]['additional_img']['img'] != 'Missing':
                try:
                    self.image_lab = tk.Label(self.main_area, highlightthickness=0, borderwidth=0,
                                              image=self.help_pages[self.page_number]['additional_img']['img'])
                except:
                    self.image_lab = tk.Label(self.main_area, highlightthickness=0, borderwidth=0,
                                              image=ImageTk.PhotoImage(
                                                  Image.new(mode="RGB", size=(740, 600), color=(46, 46, 46))))
            else:
                self.image_lab = tk.Label(self.main_area, highlightthickness=0, borderwidth=0, image=ImageTk.PhotoImage(
                    Image.new(mode="RGB", size=(740, 600), color=(46, 46, 46))))
            self.image_lab.place(x=self.help_pages[self.page_number]['additional_img']['x'],
                                 y=self.help_pages[self.page_number]['additional_img']['y'], anchor="nw")
        self.help_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.help_frame.place(relx=self.help_pages[self.page_number]['rel_x'],
                              rely=self.help_pages[self.page_number]['rel_y'], anchor="center",
                              width=self.help_pages[self.page_number]['width'],
                              height=self.help_pages[self.page_number]['height'])

        title = tk.Label(self.help_frame, text=f"Help section ({self.page_number + 1}/{len(self.help_pages)})",
                         font=("Segoe UI", 12, "bold"), bg=overlays_color, fg="white")
        title.pack(pady=7)
        tk.Label(self.help_frame, text=self.help_pages[self.page_number]['text'] if type(
            self.help_pages[self.page_number]['text']) == str else (
            self.help_pages[self.page_number]['text']['true'] if (
                self.current_state == 'initial' if self.help_pages[self.page_number]['text'][
                                                       'condition'] == 'self.current_state' else False) else
            self.help_pages[self.page_number]['text']['false']), font=("Segoe UI", 10), bg=overlays_color, fg="white",
                 wraplength=360).pack(pady=3)

        def close_command():
            self.enable_sidebar()
            self.ability_to_exit = True
            self.help_frame.destroy()
            try:
                self.image_lab.destroy()
            except:
                None
            self.set_initial_state()

        # Changing current help section page.
        def n_p_page(page_number):
            try:
                self.image_lab.destroy()
            except:
                None
            self.help_frame.destroy()
            self.page_number = page_number % (len(self.help_pages))
            self.show_help_overlay()

        ttk.Button(self.help_frame, text="Close", command=close_command, width=5).pack(side="left", padx=75, pady=5)
        ttk.Button(self.help_frame, text="<", width=2, command=lambda: n_p_page(self.page_number - 1)).pack(side="left",
                                                                                                            padx=10,
                                                                                                            pady=5)
        ttk.Button(self.help_frame, text=">", width=2, command=lambda: n_p_page(self.page_number + 1)).pack(side="left",
                                                                                                            padx=10,
                                                                                                            pady=5)

    # Advanced options.
    # Overlay which is shown when pressing "Advanced" in the options menu.
    def show_advanced_overlay(self):
        self.advanced_overlay = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.advanced_overlay.place(relx=0.5, rely=0.5, anchor="center", width=320, height=450)

        tk.Label(self.advanced_overlay, text="Advanced", font=("Segoe UI", 12, "bold"), bg=overlays_color,
                 fg="white").pack(pady=10)

        self.range1 = tk.IntVar(value=config["advanced"]["threads"])  # Amount of threads, used for range
        self.range1_int = tk.IntVar(
            value=config["advanced"]["threads"])  # Amount of threads INT, used for everything else
        self.range2 = tk.IntVar(value=config["advanced"]["posts_per_thread"])  # Posts per thread, used for range
        self.range2_int = tk.IntVar(
            value=config["advanced"]["posts_per_thread"])  # Posts per thread, used for everything else
        self.adv_option = tk.StringVar(value=config["advanced"]["grading"])  # Grading method

        tk.Label(self.advanced_overlay, text="Number of threads (5 default)", bg=overlays_color, fg="white").pack()
        r1_block = tk.Frame(self.advanced_overlay, bg=overlays_color)
        tk.Label(r1_block, textvariable=self.range1_int, bg=overlays_color, fg="white", width=4).pack()
        tk.Label(r1_block, text="Slower\nLess CPU\nusage", bg=overlays_color, fg="white").pack(side="left")
        ttk.Scale(r1_block, from_=1, to=50, variable=self.range1, orient="horizontal", length=150,
                  command=lambda value: self.range1_int.set(int(value.split('.')[0]))).pack(side="left")
        tk.Label(r1_block, text="Faster\nMore CPU\nusage", bg=overlays_color, fg="white").pack(side="left")
        r1_block.pack(pady=5)

        tk.Label(self.advanced_overlay, text="Posts per thread (10 default)", bg=overlays_color, fg="white").pack()
        r2_block = tk.Frame(self.advanced_overlay, bg=overlays_color)
        tk.Label(r2_block, textvariable=self.range2_int, bg=overlays_color, fg="white", width=4).pack()
        tk.Label(r2_block, text="Slower\nLess CPU\nand RAM\nusage", bg=overlays_color, fg="white").pack(side="left")
        ttk.Scale(r2_block, from_=1, to=100, variable=self.range2, orient="horizontal", length=150,
                  command=lambda value: self.range2_int.set(int(value.split('.')[0]))).pack(side="left")
        tk.Label(r2_block, text="Faster\nMore CPU\nand RAM\nusage", bg=overlays_color, fg="white").pack(side="left")
        r2_block.pack(pady=5)

        # Making it possible to select only one grading method
        def select_adv_option(option):
            self.adv_option.set(option.lower())
            if option.lower() == "max":
                self.opt0.state(["disabled"])
                self.opt1.state(["!disabled"])
            else:
                self.opt0.state(["!disabled"])
                self.opt1.state(["disabled"])

        options_frame = tk.Frame(self.advanced_overlay, bg=overlays_color)
        tk.Label(options_frame, text="Grading\nmethod", bg=overlays_color, fg="white").pack(side="left", padx=5)
        self.opt0 = ttk.Button(options_frame, text="MAX", width=5, padding=3, command=lambda: select_adv_option("MAX"))
        self.opt1 = ttk.Button(options_frame, text="AVG", width=5, padding=3, command=lambda: select_adv_option("AVG"))
        self.opt0.pack(side="left", padx=5)
        self.opt1.pack(side="left", padx=5)
        options_frame.pack(pady=10)
        select_adv_option(self.adv_option.get())

        tk.Label(self.advanced_overlay,
                 text="- MAX: finding the best match with favorites. (DEFAULT)\n- AVG: calculating an average match with ALL favorites.",
                 justify="left", bg=overlays_color, fg="white").pack(pady=10)

        def advanced_exit_command():
            if int(self.range1_int.get()) != config["advanced"]["threads"] or int(self.range2_int.get()) != \
                    config["advanced"]["posts_per_thread"] or self.adv_option.get().lower() != config["advanced"][
                "grading"]:
                config["advanced"]["threads"] = int(self.range1_int.get())
                config["advanced"]["posts_per_thread"] = int(self.range2_int.get())
                config["advanced"]["grading"] = self.adv_option.get().lower()
                write_to_config(config)
            self.advanced_overlay.destroy()
            self.disable_sidebar()
            self.show_options_overlay()

        ttk.Button(self.advanced_overlay, text="Close", command=advanced_exit_command).pack(pady=10, padx=10)

    # Blacklist
    # Overlay shown when pressing on "Blacklist" in the options menu.
    def show_blacklist_overlay(self):
        self.blacklist_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.blacklist_frame.place(relx=0.5, rely=0.5, anchor="center", width=300, height=485)

        title = tk.Label(self.blacklist_frame, text="Blacklist", font=("Segoe UI", 12, "bold"), bg=overlays_color,
                         fg="white")
        title.pack(pady=3)
        desc = tk.Label(self.blacklist_frame, text="Tags you DON'T want to be recommended.", font=("Segoe UI", 10),
                        bg=overlays_color, fg="white")
        desc.pack(pady=2)
        desc = tk.Label(self.blacklist_frame,
                        text="Blacklist will be used\nwhen downloading latest and favorite posts.",
                        font=("Segoe UI", 10), bg=overlays_color, fg="white")
        desc.pack()

        # Small grey-ish section of the blacklist which cannot be editted or changed in the application.
        # It contains those three tags, that I've talked about before.
        self.default_blacklist_text = tk.Text(self.blacklist_frame, width=48, height=3, bg="#b8b890", fg="black",
                                              font=("Courier", 10), state="normal", highlightthickness=0, borderwidth=0)
        self.default_blacklist_text.pack()
        self.default_blacklist_text.insert("end", "young\nloli\nshota")
        self.default_blacklist_text.config(state="disabled")

        # Main window for blacklist, where user writes tags he wants to remove from the recommendations.
        self.blacklist_text = tk.Text(self.blacklist_frame, width=48, height=14, bg="#ffffc8", fg="black",
                                      font=("Courier", 10), state="normal", highlightthickness=0, borderwidth=0)
        self.blacklist_text.pack()
        self.blacklist_text.insert("end", '\n'.join(sorted(set(config["options"]["blacklist"]) - {"young", "loli",
                                                                                                  "shota"})))  # These three are removed here in the main window, because they are already written above in the grey-ish area

        desc = tk.Label(self.blacklist_frame,
                        text="Warning! Only one tag per line will work.\nAnd there is a limit of 10k characters total.",
                        font=("Segoe UI", 10), bg=overlays_color, fg="white")
        desc.pack()

        def blacklist_exit_command():
            blacklist_text_data_string = re.sub('\s+', '\n', self.blacklist_text.get("1.0", tk.END)).strip()[:10000]
            blacklist_text_data = ["young", "loli", "shota"] + list(
                filter(None, map(str.strip, blacklist_text_data_string.split('\n'))))
            if set(blacklist_text_data) != set(config["options"]["blacklist"]):
                config["options"]["blacklist"] = blacklist_text_data
                write_to_config(config)
            self.blacklist_frame.destroy()
            self.disable_sidebar()
            self.show_options_overlay()

        ttk.Button(self.blacklist_frame, text="Close", command=blacklist_exit_command).pack(pady=10, padx=10)

    # Options menu.
    # Overlay that is shown when "Options" button is pressed.
    def show_options_overlay(self):
        self.ability_to_exit = False
        self.options_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.options_frame.place(relx=0.5, rely=0.5, anchor="center", width=230, height=470)

        title = tk.Label(self.options_frame, text="Options", font=("Segoe UI", 12, "bold"), bg=overlays_color,
                         fg="white")
        title.pack(pady=3)
        ttk.Button(self.options_frame, text="Profile",
                   command=lambda: (config_overwrite(), self.disable_sidebar(), self.options_frame.destroy(),
                                    self.show_login_overlay(change=True))).pack(pady=5, padx=30)
        ttk.Button(self.options_frame, text="Blacklist",
                   command=lambda: (config_overwrite(), self.disable_sidebar(), self.options_frame.destroy(),
                                    self.show_blacklist_overlay())).pack(pady=5, padx=30)

        self.min_score_value = tk.IntVar(
            value=config["options"]["min_score"])  # Minimum score threshold (from -999 to 999)
        self.rating_value = tk.StringVar(
            value='Safe' if config["options"]["default_rating"] == 's' else 'Questionable' if config["options"][
                                                                                                  "default_rating"] == 'q' else 'Explicit' if
            config["options"][
                "default_rating"] == 'e' else 'Any')  # Default post rating (Safe, Questionable, Explicit, Any)
        self.auto_load = tk.BooleanVar(value=config["options"]["auto_load"])  # Auto load results
        self.logging = tk.BooleanVar(value=config["options"]["logging"])  # Logging (Debug)

        p0_frame = tk.Frame(self.options_frame, bg=overlays_color)
        tk.Label(p0_frame, text="Minimum score\nthreshold", bg=overlays_color, fg="white", justify="left").pack(
            side="left", padx=5)
        control = tk.Frame(p0_frame, bg=overlays_color)
        tk.Button(control, text="-", width=2, command=lambda: self.min_score_value.set(
            self.min_score_value.get() - 1) if self.min_score_value.get() > -999 else self.min_score_value.set(
            -999)).pack(side="left")
        self.min_entry = tk.Entry(control, textvariable=self.min_score_value, width=5, justify="center")
        self.min_entry.pack(side="left", padx=3)
        tk.Button(control, text="+", width=2, command=lambda: self.min_score_value.set(
            self.min_score_value.get() + 1) if self.min_score_value.get() < 999 else self.min_score_value.set(
            999)).pack(side="left")
        control.pack(side="right")
        p0_frame.pack(pady=10, padx=10, fill="x")
        self.min_entry.bind("<FocusOut>", lambda e, ent=self.min_entry: (self.min_score_value.set(
            0 if not ent.get().isnumeric() else -999 if int(ent.get()) < -999 else 999 if int(ent.get()) > 999 else int(
                ent.get()))))

        p1_frame = tk.Frame(self.options_frame, bg=overlays_color)
        tk.Label(p1_frame, text="Default post\nrating", bg=overlays_color, fg="white", justify="left").pack(side="left",
                                                                                                            padx=5)
        ttk.OptionMenu(p1_frame, self.rating_value, self.rating_value.get(), "Safe", "Questionable", "Explicit",
                       "Any").pack(side="right")
        p1_frame.pack(pady=10, padx=10, fill="x")

        p2_frame = tk.Frame(self.options_frame, bg=overlays_color)
        tk.Label(p2_frame, text="Auto load\nresults", bg=overlays_color, fg="white", justify="left").pack(side="left",
                                                                                                          padx=5)
        ttk.Checkbutton(p2_frame, variable=self.auto_load).pack(side="right")
        p2_frame.pack(pady=10, padx=10, fill="x")

        p3_frame = tk.Frame(self.options_frame, bg=overlays_color)
        tk.Label(p3_frame, text="Logging\n(Debug)", bg=overlays_color, fg="white", justify="left").pack(side="left",
                                                                                                        padx=5)
        ttk.Checkbutton(p3_frame, variable=self.logging).pack(side="right")
        p3_frame.pack(pady=5, padx=10, fill="x")

        def config_overwrite():
            if int(self.min_score_value.get()) != config["options"]["min_score"] or self.rating_value.get().lower()[
                0] != config["options"]["default_rating"] or self.auto_load.get() != config["options"][
                "auto_load"] or self.logging != config["options"]["logging"]:
                config["options"]["min_score"] = int(self.min_score_value.get())
                config["options"]["default_rating"] = self.rating_value.get().lower()[0]
                config["options"]["auto_load"] = self.auto_load.get()
                config["options"]["logging"] = self.logging.get()
                write_to_config(config)

        ttk.Button(self.options_frame, text="Advanced",
                   command=lambda: (config_overwrite(), self.disable_sidebar(), self.options_frame.destroy(),
                                    self.show_advanced_overlay())).pack(pady=5, padx=30)

        def options_exit_command():
            config_overwrite()
            self.options_frame.destroy()
            self.ability_to_exit = True
            self.set_initial_state()

        ttk.Button(self.options_frame, text="Close", command=options_exit_command).pack(pady=5, padx=30)

    # Failed exit attempt.
    # Shown when the process is working with thread (making it hard to properly quit the program) and the user attempts to exit
    def exit_overlay(self):
        self.exit_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.exit_frame.place(relx=0.5, rely=0.9, anchor="center", width=265, height=30)

        title = tk.Label(self.exit_frame, text="Please wait for or close a process to exit",
                         font=("Segoe UI", 10, "bold"), bg=overlays_color, fg="white")
        title.pack(pady=5)

    # Needed only to change a value of a variable and making a delay
    def show_exit_overlay(self):
        self.exit_state = 'showing'
        self.exit_overlay()
        time.sleep(1)
        self.exit_frame.destroy()
        self.exit_state = 'nothing'

    # Exit confirmation
    # Overlay shown when the user tries to exit the program and he is allowed to do so (self.ability_to_exit)
    def on_exit(self):
        if self.exit_state == 'nothing' and self.copy_state == 'nothing':
            if self.ability_to_exit:
                if self.current_state != "confirmation":
                    self.disable_sidebar()
                    self.show_confirm_overlay("Are you sure?", "You are about to exit the program.",
                                              lambda: (write_to_log('END'), self.destroy()),
                                              lambda: (self.confirm_frame.destroy(), self.set_initial_state()))
                else:
                    write_to_log('END')
                    self.destroy()
            else:
                threading.Thread(target=self.show_exit_overlay).start()

    # Loads images that are used in the help section for demonstration.
    def load_images_help(self):
        write_to_log('Loading help images...')
        for index, page in enumerate(self.help_pages):
            if page['additional_img']:
                try:
                    self.help_pages[index]['additional_img']['img'] = ImageTk.PhotoImage(
                        Image.open(page['additional_img']['img']))
                except:
                    self.help_pages[index]['additional_img']['img'] = "Missing"
            self.progress_img["value"] = (index + 1) / len(self.help_pages) * 100
        self.enable_sidebar()
        self.help_loaded = True
        self.ability_to_exit = True
        self.loading_frame_img.destroy()
        write_to_log("Loading help images completed.")

    # Initial state
    # It does a couple of check, and might actually just skip over the initial state entirely.
    # After confirmation, program will set itself to initial state, or in other words, run this function.
    # But it is also launched in some other areas of the code.
    def set_initial_state(self):
        write_to_log('Initial state.')
        self.disable_sidebar()
        self.current_state = 'initial'
        try:
            self.loading_frame.destroy()
        except:
            None
        login = config['profile']['login']
        api_key = config['profile']['API_key']

        # If login is empty, remove all loaded images, request user to provide account information.
        if not login.strip() or len(login.strip()) > 100 or len(api_key.strip())>100:
            write_to_log('Profile is missing or bad. Authorization requested.')
            self.ability_to_exit = True
            self.disable_sidebar()
            self.show_login_overlay()
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            label = tk.Label(self.scrollable_frame, text="Nobody here but us chickens!", fg="white",
                             bg=scrollable_area_color, font=("Segoe UI", 14))
            label.pack(pady=20)

        # Login and API key is OK and Auto Load is set to True, then change state to a 'completed' one
        elif config['options']['auto_load']:
            if api_key.strip():
                session.auth = HTTPBasicAuth(login.replace(' ','_'), api_key)
            else:
                session.auth = None
            self.ability_to_exit = False
            self.set_completed_state()

        # Auto load is False, show a generic screen with no results loaded yet.
        else:
            write_to_log('Profile exists.')
            if api_key.strip():
                session.auth = HTTPBasicAuth(login.replace(' ','_'), api_key)
            else:
                session.auth = None
            self.ability_to_exit = True
            self.enable_sidebar()
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            label = tk.Label(self.scrollable_frame, text="Nobody here but us chickens!", fg="white",
                             bg=scrollable_area_color, font=("Segoe UI", 14))
            label.pack(pady=20)
            if not self.help_loaded:
                self.disable_sidebar()
                self.ability_to_exit = False
                self.show_loading_images_overlay()
                threading.Thread(target=self.load_images_help).start()

    # Needed only when the user confirms the overwriting of previous results in the "Start" process, when current state is 'completed'
    def y_confirmation_initial(self):
        self.confirm_frame.destroy()
        self.final_res = {}
        self.current_state = 'loading'
        self.ability_to_exit = False
        threading.Thread(target=self.start_process).start()

    # Function of the "Load" button, set completed state so that it will load results.
    def load_process(self):
        self.disable_sidebar()
        self.ability_to_exit = False
        self.set_completed_state()

    # The only thing it does is set a couple of variables to different states, and run a seperate function to actually start the whole recommendation process.
    def start_process(self):
        self.cancel_loading = False
        self.disable_sidebar()
        config_for_log = copy.deepcopy(config)
        config_for_log['profile']['API_key'] = '[HIDDEN]'
        login = config['profile']['login'].replace(' ', '_')
        write_to_log(f'Current config: {config_for_log}')
        write_to_log('Mandatory check of the profile...')
        if not self.check_state:
            try:
                params = {"tags": f'fav:{login}'}
                req = session.get(f'https://e621.net/posts.json', params=params)
                res = req.status_code
                try:
                    js = req.json()
                except:
                    js = {"posts":[]}
            except:
                res = -1
            time.sleep(INTENTIONAL_DELAY)
            if res == 200 and len(js.get("posts"))>0:
                self.check_state = True
                write_to_log('Success.')
                if self.current_state == 'completed':
                    self.show_confirm_overlay("Are you sure?",
                                              "When this process finishes, the previous results will be gone.",
                                              self.y_confirmation_initial,
                                              lambda: (self.confirm_frame.destroy(), self.set_initial_state()))
                else:
                    self.current_state = "loading"
                    self.show_loading_overlay()
                    threading.Thread(target=self.load_data).start()
            else:
                write_to_log('Incorrect profile. Authorization requested.')
                self.check_state = False
                self.current_state = 'initial'
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()
                label = tk.Label(self.scrollable_frame, text="Nobody here but us chickens!", fg="white",
                                 bg=scrollable_area_color, font=("Segoe UI", 14))
                label.pack(pady=20)
                self.ability_to_exit = True
                self.show_login_overlay(error=True)
        else:
            if self.current_state == 'completed':
                self.show_confirm_overlay("Are you sure?",
                                          "When this process finishes, the previous results will be gone.",
                                          self.y_confirmation_initial,
                                          lambda: (self.confirm_frame.destroy(), self.set_initial_state()))
            else:
                self.current_state = "loading"
                self.show_loading_overlay()
                threading.Thread(target=self.load_data).start()

    # Runs when the "Start" button is pressed
    def start_process_thread(self):
        self.ability_to_exit = False
        threading.Thread(target=self.start_process).start()

    # When some kind of process is running right now, the sidebar on the right side of the window is blocked off, so that the user won't mess something up.
    # Additionally it will lock the scrollable area with preview images and everything.
    # do_not_copy - will tell the function to remove the ability to copy post links in the scrollable area if the parameter is False
    def disable_sidebar(self, do_not_copy=False):
        for child in self.sidebar.winfo_children():
            child.config(state="disabled")
        self.canvas.unbind_all("<MouseWheel>")
        self.scrollbar.config(command=lambda *args: None)
        if not do_not_copy:
            for widget in self.scrollable_frame.winfo_children():
                widget.unbind("<Button-1>")
                for child in widget.winfo_children():
                    child.unbind("<Button-1>")
                    if "winfo_children" in dir(child):
                        for another_child in child.winfo_children():
                            another_child.unbind("<Button-1>")

    # The opposite. It will activate every button on the sidebar and unlock scrollable area.
    def enable_sidebar(self):
        for child in self.sidebar.winfo_children():
            child.config(state="normal")
        self.scrollbar.config(command=self.canvas.yview)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    # Activates when "Login" button is pressed on the login overlay.
    # It will run some checks to confirm the functionality of the account and the profile.
    # If something goes wrong, then the user will be notified.
    def login_command(self):
        login = self.login_entry.get()
        api_key = self.api_entry.get()
        if not login.strip() or len(login.strip()) > 100 or len(api_key.strip())>100:
            self.login_entry.configure(highlightbackground="red", highlightcolor="red")
        else:
            self.login_entry.configure(highlightbackground="white", highlightcolor="white")

        if login.strip() and len(login.strip()) <= 100 and len(api_key.strip())<=100:
            config['profile']['login'] = login
            if api_key.strip():
                config['profile']['API_key'] = api_key
                session.auth = HTTPBasicAuth(login.replace(' ','_'), api_key)
            else:
                config['profile']['API_key'] = ''
                session.auth = None
            write_to_config(config)
            login_cleaned = login.replace(' ', '_')
            self.login_frame.destroy()
            try:
                params = {"tags": f'fav:{login_cleaned}'}
                req = session.get(f"https://e621.net/posts.json", params=params)
                res = req.status_code
                try:
                    js = req.json()
                except:
                    js = {"posts":[]}
            except:
                res = -1
            time.sleep(INTENTIONAL_DELAY)
            if res == 200 and len(js.get("posts"))>0:
                self.check_state = True
                self.after(100, self.set_initial_state)
            else:
                self.check_state = False
                self.current_state = 'initial'
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()
                label = tk.Label(self.scrollable_frame, text="Nobody here but us chickens!", fg="white",
                                 bg=scrollable_area_color, font=("Segoe UI", 14))
                label.pack(pady=20)
                self.ability_to_exit = True
                self.show_login_overlay(error=True)

    # There are multiple areas of code where a simple confirmation window is required.
    # So this is a function that allows to create just that.
    def show_confirm_overlay(self, title, message, y_command, n_command):
        self.confirm_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.confirm_frame.place(relx=0.5, rely=0.5, anchor="center", width=400, height=200)

        title = tk.Label(self.confirm_frame, text=title, font=("Segoe UI", 12, "bold"), bg=overlays_color, fg="white")
        title.pack(pady=7)
        if type(message) != list:
            tk.Label(self.confirm_frame, text=message, font=("Segoe UI", 10), bg=overlays_color, fg="white").pack(
                pady=7)
        else:
            for msg in message:
                tk.Label(self.confirm_frame, text=msg, font=("Segoe UI", 10), bg=overlays_color, fg="white").pack(
                    pady=5)

        ttk.Button(self.confirm_frame, text="Yes", command=y_command).pack(side=tk.LEFT, pady=5, padx=30)
        ttk.Button(self.confirm_frame, text="No", command=n_command).pack(side=tk.RIGHT, pady=5, padx=30)

    # Login/Profile
    # Overlay shown when user needs or wants to change their account in the application
    # error - will show the overlay in an "error" state, when the profile is wrong or there is no connection to e621
    # change - when the user already has a proper profile, but now he wants to change it or view it (occurs when the "Profile" button is pressed in the options menu)
    def show_login_overlay(self, error=False, change=False):
        self.login_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.login_frame.place(relx=0.5, rely=0.5, anchor="center", width=400, height=300 if not change else 350)

        if error:
            title = tk.Label(self.login_frame,
                             text="Invalid login or API key is needed.\nOr there is no connection to e621.",
                             font=("Segoe UI", 12, "bold"),
                             bg=overlays_color, fg="white")
            title.pack(pady=3)
        elif not change:
            title = tk.Label(self.login_frame, text="Please login.", font=("Segoe UI", 12, "bold"), bg=overlays_color,
                             fg="white")
            title.pack(pady=7)
        else:
            title = tk.Label(self.login_frame, text="Profile", font=("Segoe UI", 12, "bold"), bg=overlays_color,
                             fg="white")
            title.pack(pady=7)

        title = tk.Label(self.login_frame, text="Login/Username", font=("Segoe UI", 10), bg=overlays_color, fg="white")
        title.pack(pady=5)

        login_text = tk.StringVar()  # Username/Login
        login_text.set(config["profile"]["login"])
        self.login_entry = tk.Entry(self.login_frame, textvariable=login_text, justify=tk.CENTER, font=("Segoe UI", 10),
                                    highlightthickness=2)
        self.login_entry.pack(pady=7, ipadx=30, ipady=5)

        self.login_entry.bind("<FocusOut>", lambda e, ent=self.login_entry: (login_text.set(ent.get()[:100])))

        title = tk.Label(self.login_frame, text="API key (optional)",
                         font=font.Font(family="Segoe UI", size=10, underline=True),
                         bg=overlays_color, fg="white")
        title.pack(pady=5)
        title.bind("<Button-1>", lambda e: (pyperclip.copy('https://e621.net/help/api'), threading.Thread(
            target=self.show_copy_overlay).start() if self.copy_state == 'nothing' else None))

        api_text = tk.StringVar()  # API key
        api_text.set(config["profile"]["API_key"])
        self.api_entry = tk.Entry(self.login_frame, textvariable=api_text, justify=tk.CENTER, font=("Segoe UI", 10),
                                  highlightthickness=2, show="•")
        self.api_entry.pack(pady=10, ipadx=30, ipady=5)

        self.api_entry.bind("<FocusOut>", lambda e, ent=self.api_entry: (api_text.set(ent.get()[:100])))

        if error:
            self.login_entry.configure(highlightbackground="red", highlightcolor="red")
            self.api_entry.configure(highlightbackground="red", highlightcolor="red")
            config["profile"]["login"] = ''
            config["profile"]["API_key"] = ''
            write_to_config(config)
        else:
            self.login_entry.configure(highlightbackground="white", highlightcolor="white")
            self.api_entry.configure(highlightbackground="white", highlightcolor="white")

        ttk.Button(self.login_frame, text="Login", command=self.login_command).pack(pady=10, padx=10)
        if change:
            ttk.Button(self.login_frame, text="Close",
                       command=lambda: (self.login_frame.destroy(), self.disable_sidebar(),
                                        self.show_options_overlay())).pack(pady=10, padx=10)

    # Function to cancel the recommendation system. Happens when the "Cancel" button in the loading overlay is pressed.
    def cancel_command(self):
        self.cancel_loading = True
        if self.data_state == 'error':
            threading.Thread(target=self.load_data).start()

    # Loading overlay
    # Shown when the recommendation system has started and now is showing the current progress of the whole process.
    def show_loading_overlay(self):
        self.loading_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.loading_frame.place(relx=0.5, rely=0.5, anchor="center", width=400, height=250)

        title = tk.Label(self.loading_frame, text="Loading, please wait...", font=("Segoe UI", 12, "bold"),
                         bg=overlays_color, fg="white")
        title.pack(pady=5)

        self.console = tk.Text(self.loading_frame, width=48, height=6, bg="black", fg="white", font=("Courier", 10),
                               state="normal")
        self.console.config(state="disabled")
        self.console.pack(pady=5)

        self.progress = ttk.Progressbar(self.loading_frame, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(pady=5)
        self.progress["value"] = 0

        self.cancel = ttk.Button(self.loading_frame, text="Cancel", command=self.cancel_command)
        self.cancel.pack(pady=10, padx=10)

    # This will write new information to the "console" window in the loading overlay
    def log_to_console(self, message, one_line=False, special=False):
        if not self.cancel_loading or special:
            self.console.config(state="normal")
            if one_line:
                self.console.delete("end-2l", "end-1l")
            self.console.insert("end", message + "\n")
            self.console.see("end")
            self.console.config(state="disabled")

    # Downloading favorite posts
    # Will download them page-by-page with 320 posts in a single page.
    # Favorites will also be filtered with a blacklist.
    def download_fav_posts(self, blacklist, login):
        write_to_log('Downloading favorite posts...')
        blacklist = set(filter(None, map(str.strip, blacklist)))
        blacklist.update({"young", "loli", "shota"})
        login = login.replace(' ', '_')
        self.log_to_console("Downloading favorite posts...")
        i = 1
        try:
            fav = pd.DataFrame(columns=['id',
                                        'tag_string'])  # This DataFrame will contain filtered posts, that will be later converted to a csv file.
            params = {"limit": 320, "tags": f'fav:{login}', "page": i}
            req = session.get(f'https://e621.net/posts.json', params=params)
            time.sleep(INTENTIONAL_DELAY)
            res = req.status_code
            if res == 200:
                js = req.json()
                while js.get('posts'):
                    if i == 1:
                        self.log_to_console(f'Downloading page #{i}')
                    else:
                        self.log_to_console(f'Downloading page #{i}', one_line=True)
                    write_to_log(f'Downloading page #{i}')
                    temp_fav = pd.DataFrame(js.get('posts'))
                    temp_fav_tags = pd.DataFrame.from_records(temp_fav['tags'])
                    temp_fav['tag_string'] = temp_fav_tags['general'] + temp_fav_tags['artist'] + temp_fav_tags[
                        'character'] + temp_fav_tags['species'] + temp_fav_tags['meta'] + temp_fav_tags['lore']
                    del temp_fav_tags
                    temp_fav = temp_fav[[not bool(blacklist.intersection(set(row))) for row in temp_fav[
                        'tag_string']]]  # The filter itself. Will clear all the posts that contains any of the blacklisted tags.
                    if len(temp_fav) > 0:
                        temp_fav['tag_string'] = temp_fav['tag_string'].str.join(', ')
                        fav = pd.concat([fav, temp_fav[['id', 'tag_string']]])
                    del temp_fav
                    if self.cancel_loading:
                        break
                    i += 1
                    params = {"limit": 320, "tags": f'fav:{login}', "page": i}
                    req = session.get(f'https://e621.net/posts.json', params=params)
                    time.sleep(INTENTIONAL_DELAY)
                    res = req.status_code
                    if res == 200:
                        js = req.json()
                    elif res == 403:
                        self.data_state = 'error'
                        self.log_to_console(f"Error! Your favorites are hidden!")
                        self.log_to_console("Please cancel the process and input your API key in the profile section.")
                        write_to_log(f'Error. Response from e6: {res}')
                        break
                    else:
                        self.data_state = 'error'
                        self.log_to_console(f"Error! Response from the e6: {res}")
                        self.log_to_console("Please cancel the process and try again later.")
                        write_to_log(f'Error. Response from e6: {res}')
                        break
                if i == 1:
                    self.data_state = 'error'
                    self.log_to_console("Not a single post was found.")
                    self.log_to_console("You might not have favorited any post yet or options are too strict.")
                    self.log_to_console("The program will not work without a single post being favorited.")
                    self.log_to_console("Please cancel the process and try again later.")
                    write_to_log('Not a single post was found.')
            elif res == 403:
                self.data_state = 'error'
                self.log_to_console(f"Error! Your favorites are hidden!")
                self.log_to_console("Please cancel the process and input your API key in the profile section.")
                write_to_log(f'Error. Response from e6: {res}')
            else:
                self.data_state = 'error'
                self.log_to_console(f"Error! Response from e6: {res}")
                self.log_to_console("Please cancel the process and try again later.")
                write_to_log(f'Error. Response from e6: {res}')
        except Exception as a:
            write_to_log(f'Error.\n{a}')
            self.data_state = 'error'
            self.log_to_console('Something went horribly wrong!')
            self.log_to_console("Please cancel the process and try again later.")
        if self.cancel_loading or self.data_state == 'error':
            write_to_log('Process is incomplete. Favorite posts failed.')
        else:
            try:
                fav.set_index('id').to_csv('csv_files/fav_posts/fav_posts.csv')
                del fav
                try:
                    del temp_fav
                except:
                    None
            except:
                None

    # Downloading latest posts
    # "Latest" means five pages of posts uploaded recently.
    # A filter here is a bit more complex, as it now uses not only blacklist, but also min score threshold and default rating, with additional check for any favorited posts.
    def download_latest_posts(self, date_today, blacklist, login, min_score_threshold=0, default_rating='s',
                              favorites_hidden=False):
        if not favorites_hidden:
            write_to_log("Downloading latest posts...")
        blacklist = set(filter(None, map(str.strip, blacklist)))
        blacklist.update({"young", "loli", "shota"})
        login = login.replace(' ', '_')  # If login has whitespaces, convert them to a proper format for the request url
        if not favorites_hidden:
            self.log_to_console("Downloading latest posts...")
        i = 1
        pages_to_download = 5  # This is how many pages of recent posts will be downloaded
        try:
            lat = pd.DataFrame(columns=['id', 'tag_string', 'url', 'ext'])
            if default_rating != 'a':
                if favorites_hidden:
                    params = {"limit": 320, "tags": f'rating:{default_rating}',
                              "page": i}  # Only get posts that have a matching rating with the set one
                else:
                    params = {"limit": 320, "tags": f'rating:{default_rating} -fav:{login}',
                              "page": i}  # Only get posts that are not favorited and have a matching rating with the set one
            else:
                if favorites_hidden:
                    params = {"limit": 320, "page": i}  # Get every post
                else:
                    params = {"limit": 320, "tags": f'-fav:{login}', "page": i}  # Only get posts that are not favorited
            req = session.get(f'https://e621.net/posts.json', params=params)

            time.sleep(INTENTIONAL_DELAY)
            res = req.status_code
            if res == 200:
                js = req.json()
                while js.get('posts') and i <= pages_to_download:
                    if i == 1:
                        self.log_to_console(f'Downloading page #{i}')
                    else:
                        self.log_to_console(f'Downloading page #{i}', one_line=True)
                    write_to_log(f'Downloading page #{i}')
                    temp_lat = pd.DataFrame(js.get('posts'))
                    temp_lat["total"] = pd.DataFrame.from_records(temp_lat["score"])["total"]
                    temp_lat['url'] = pd.DataFrame.from_records(temp_lat['preview'])['url']
                    temp_lat['ext'] = pd.DataFrame.from_records(temp_lat['file'])['ext']
                    temp_lat_tags = pd.DataFrame.from_records(temp_lat['tags'])
                    temp_lat['tag_string'] = temp_lat_tags['general'] + temp_lat_tags['artist'] + temp_lat_tags[
                        'character'] + temp_lat_tags['species'] + temp_lat_tags['meta'] + temp_lat_tags['lore']
                    del temp_lat_tags
                    temp_lat = temp_lat[(temp_lat["total"] >= min_score_threshold) & (pd.Series(
                        [not bool(blacklist.intersection(set(row))) for row in
                         temp_lat['tag_string']]))]  # The filter, based on min score threshold and blacklist

                    if len(temp_lat) > 0:
                        temp_lat['tag_string'] = temp_lat['tag_string'].str.join(', ')
                        lat = pd.concat([lat, temp_lat[['id', 'tag_string', 'url', 'ext']]])
                    del temp_lat
                    if self.cancel_loading:
                        break
                    i += 1
                    if default_rating != 'a':
                        if favorites_hidden:
                            params = {"limit": 320, "tags": f'rating:{default_rating}',
                                      "page": i}  # Only get posts that have a matching rating with the set one
                        else:
                            params = {"limit": 320, "tags": f'rating:{default_rating} -fav:{login}',
                                      "page": i}  # Only get posts that are not favorited and have a matching rating with the set one
                    else:
                        if favorites_hidden:
                            params = {"limit": 320, "page": i}  # Get every post
                        else:
                            params = {"limit": 320, "tags": f'-fav:{login}',
                                      "page": i}  # Only get posts that are not favorited
                    req = session.get(f'https://e621.net/posts.json', params=params)
                    time.sleep(INTENTIONAL_DELAY)
                    res = req.status_code
                    if res == 200:
                        js = req.json()
                    else:
                        self.data_state = 'error'
                        self.log_to_console(f"Error! Response from the e6: {res}")
                        self.log_to_console("Please cancel the process and try again later.")
                        write_to_log(f'Error. Response from e6: {res}')
                        break
                if i == 1 or len(lat) <= 0:
                    self.data_state = 'error'
                    self.log_to_console("Not a single post was found.")
                    self.log_to_console("The program will recommend nothing.")
                    self.log_to_console("Your options might be too strict or no post was found.")
                    self.log_to_console("Please cancel the process and try again later.")
                    write_to_log(f'Error. Response from e6: {res}')
            elif res == 403:  # If favorites are suddenly hidden, attempt to download latest posts without knowing if they are favorited.
                write_to_log(f'Favorites are hidden. Attempting to use a different method...')
                self.download_latest_posts(today, config['options']["blacklist"], config['profile']['login'],
                                           config['options']["min_score"], config['options']["default_rating"],
                                           favorites_hidden=True)
                return None
            else:
                self.data_state = 'error'
                self.log_to_console(f"Error! Response from the e6: {res}")
                self.log_to_console("Please cancel the process and try again later.")
                write_to_log(f'Error. Response from e6: {res}')
        except Exception as a:
            write_to_log(f'Error.\n{a}')
            self.data_state = 'error'
            self.log_to_console('Something went horribly wrong!')
            self.log_to_console("Please cancel the process and try again later.")
        if self.cancel_loading or self.data_state == 'error':
            write_to_log('Process is incomplete. Latest posts failed.')
        else:
            try:
                # Attempt to remove previously downloaded latest posts, to replace it with the new one.
                for filename in os.listdir('csv_files/latest_posts/'):
                    file_path = os.path.join('csv_files/latest_posts/', filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        write_to_log('Failed to delete %s. Reason: %s' % (file_path, e))
                lat.set_index('id').to_csv(f'csv_files/latest_posts/latest_posts_{date_today}.csv')
                del lat
                try:
                    del temp_lat_tags
                except:
                    None
                try:
                    del temp_lat
                except:
                    None
            except:
                None

    # Recommendation system itself.
    def recommendations(self, threads=5, posts_for_each=100, method="max"):
        write_to_log('Recommendation system started.')

        # Check if the favorites and recent posts were downloaded successfully and that they match the format.
        self.log_to_console("Loading favorite posts...")
        try:
            fav_files = os.listdir('csv_files/fav_posts')
            fav_file = sorted(fav_files)[-1]
            fav = pd.read_csv(f'csv_files/fav_posts/{fav_file}')
        except (FileNotFoundError, IndexError):
            self.data_state = 'error'
            self.cancel.config(state="normal")
            self.log_to_console('Favorite posts went missing!')
            self.log_to_console("Please cancel the process and re-download favorite posts.")
            return None
        if 'id' not in fav.columns or 'tag_string' not in fav.columns or len(fav) <= 0:
            self.data_state = 'error'
            self.cancel.config(state="normal")
            self.log_to_console('Favorite posts are invalid!')
            self.log_to_console('Please cancel the process and re-download favorite posts.')
            return None
        self.log_to_console("Loading latest posts...")
        try:
            lat_files = os.listdir('csv_files/latest_posts')
            lat_file = sorted(lat_files)[-1]
            lat = pd.read_csv(f'csv_files/latest_posts/{lat_file}')
        except (FileNotFoundError, IndexError):
            self.data_state = 'error'
            self.cancel.config(state="normal")
            self.log_to_console("Latest posts went missing!")
            self.log_to_console("Please cancel the process and re-download latest posts.")
            return None
        if 'id' not in lat.columns or 'tag_string' not in lat.columns or 'url' not in lat.columns or 'ext' not in lat.columns or len(
                lat) <= 0:
            self.data_state = 'error'
            self.cancel.config(state="normal")
            self.log_to_console("Latest posts are invalid!")
            self.log_to_console('Please cancel the process and re-download latest posts.')
            return None

        write_to_log('Everything is fine with the data.')

        # The algorithm that uses cosine similarity to calculate a grade of similarity between all the favorites and a group of latest posts
        def calculate_match(ratings, countV, fav, part_of_lat, method):
            favlat = pd.concat([fav['tag_string'], part_of_lat['tag_string']])
            countV_matrix = countV.fit_transform(favlat)
            cosine_sim = cosine_similarity(countV_matrix[len(fav):], countV_matrix[:len(fav)])
            indiceslat = pd.Series(part_of_lat['id'], index=part_of_lat.index)
            if method == "max":
                result = {
                    int(indiceslat[el[0]]): [part_of_lat.iloc[el[0]]["url"], max(el[1]), part_of_lat.iloc[el[0]]["ext"]]
                    for el in enumerate(cosine_sim)}
            else:
                result = {int(indiceslat[el[0]]): [part_of_lat.iloc[el[0]]["url"], sum(el[1]) / len(el[1]),
                                                   part_of_lat.iloc[el[0]]["ext"]] for el in enumerate(cosine_sim)}

            ratings.update(result)

        # This will create new threads, where each will run their own calculate_match function with their group of latest posts
        def thread_manager(ratings, countV, fav, lat, threads, posts_for_each, method="max"):
            progress = (100 - ceil((list(ratings.values()).count(-1) / len(ratings)) * 100))
            self.progress["value"] = progress
            self.loading_frame.update_idletasks()
            j = 0
            while progress != 100:
                t = []
                for i in range(threads):
                    part_of_lat = lat[0 + j * posts_for_each:posts_for_each + j * posts_for_each].reset_index().drop(
                        'index', axis=1)
                    if len(part_of_lat) <= 0:
                        break
                    t += [threading.Thread(target=calculate_match, args=(ratings, countV, fav, part_of_lat, method))]
                    t[i].start()
                    j += 1
                try:
                    t[-1].join()
                except:
                    None
                progress = (100 - ceil((list(ratings.values()).count(-1) / len(ratings)) * 100))
                self.progress["value"] = progress
                self.loading_frame.update_idletasks()

        countV = CountVectorizer(stop_words=None)
        ratings = dict.fromkeys(lat['id'], -1)  # A dictionary containing grades for every latest post
        self.log_to_console("Starting recommendation service...")
        self.log_to_console(f"Chosen method: {method}")
        fav.drop_duplicates(subset=['id'], inplace=True)
        lat.drop_duplicates(subset=['id'], inplace=True)
        before = time.time()
        thread_manager(ratings, countV, fav, lat, threads, posts_for_each, method)
        write_to_log(f"Done. Saving the results... (+ Downloading previews for top recommendations)")
        self.log_to_console('Saving the results...')
        self.progress["value"] = 0
        final_res = list(dict(sorted(ratings.items(), key=lambda x: x[1][1], reverse=True)).items())
        # Replacing urls with base64 preview images for the top results
        for i, res in enumerate(final_res):
            if i < self.how_many_images_to_download:
                self.progress["value"] = (i / (self.how_many_images_to_download - 1)) * 100
                try:
                    response = session.get(res[1][0])
                    img_data = response.content
                    time.sleep(INTENTIONAL_DELAY)
                    res[1][0] = base64.b64encode(img_data).decode()
                except Exception as a:
                    write_to_log(f'Error.\n{a}')
                    self.log_to_console('Something went wrong. Attemping to save at least something...')
                    break
            else:
                break
        with open("csv_files/results/results.json", 'w', encoding='utf-8') as f:
            json.dump(dict(final_res), f)
        after = time.time()
        write_to_log("Completed.")
        self.log_to_console('Done!')
        self.log_to_console(f"Time it took: {round(after - before, 5)} seconds")

    # The main "Start" process.
    # It will download everything and run recommendation system.
    # During all of this, an error can occur, so it will handle it as best as it can.
    def load_data(self):
        # Create missing folders
        if self.data_state == 'start':
            write_to_log('The process began!')
            if not os.path.exists('csv_files/'):
                os.mkdir('csv_files')
            if not os.path.exists('csv_files/fav_posts'):
                os.mkdir('csv_files/fav_posts')
            if not os.path.exists('csv_files/latest_posts'):
                os.mkdir('csv_files/latest_posts')
            if not os.path.exists('csv_files/results'):
                os.mkdir('csv_files/results')
            self.log_to_console("Checking favorite posts...")
            self.data_state = 'fav'
        # Download favorite posts (ask to confirm over-write if there is already downloaded posts in the folder)
        if self.data_state == 'fav':
            if not os.listdir('csv_files/fav_posts'):
                self.download_fav_posts(config['options']["blacklist"], config['profile']['login'])
                if self.data_state != 'error':
                    self.log_to_console("Checking latest posts...")
                    if not self.cancel_loading:
                        self.data_state = 'lat'
                    self.data_response = [None]
            else:
                if self.data_response[0] == None:
                    write_to_log('Existing instance of favorite posts was found.')
                    self.show_confirm_overlay("Favorite posts", "Do you want to re-download your favorite posts?",
                                              lambda: (self.confirm_frame.destroy(),
                                                       self.data_response.__setitem__(0, True),
                                                       threading.Thread(target=self.load_data).start()),
                                              lambda: (self.confirm_frame.destroy(),
                                                       self.data_response.__setitem__(0, False),
                                                       threading.Thread(target=self.load_data).start()))
                elif self.data_response[0]:
                    self.download_fav_posts(config['options']["blacklist"], config['profile']['login'])
                    if self.data_state != 'error':
                        self.log_to_console("Checking latest posts...")
                        if not self.cancel_loading:
                            self.data_state = 'lat'
                        self.data_response = [None]
                else:
                    if self.data_state != 'error':
                        self.log_to_console("Checking latest posts...")
                        if not self.cancel_loading:
                            self.data_state = 'lat'
                        self.data_response = [None]
        # Download latest posts (ask to confirm the over-write if there is already downloaded posts in the folder, or inform the user if the posts are outdated or probably are not updated yet)
        if self.data_state == 'lat':
            if not os.listdir('csv_files/latest_posts'):
                self.download_latest_posts(today, config['options']["blacklist"], config['profile']['login'],
                                           config['options']["min_score"], config['options']["default_rating"])
                if self.data_state != 'error':
                    if not self.cancel_loading:
                        self.data_state = 'rec'
                    self.data_response = [None]
            else:
                files = os.listdir('csv_files/latest_posts')
                latest_file = sorted(files)[-1]
                file_date = re.findall('latest_posts_(\d{4}-\d{2}-\d{2})\.csv', latest_file)
                if file_date:
                    file_date = file_date[0]
                    if datetime.strptime(file_date, "%Y-%m-%d") < datetime.strptime(str(today), "%Y-%m-%d"):
                        if self.data_response[0] == None:
                            write_to_log('Outdated latest posts was found.')
                            self.show_confirm_overlay("Latest posts", ["The database is outdated.",
                                                                       f'The last update was {(datetime.strptime(str(today), "%Y-%m-%d") - datetime.strptime(file_date, "%Y-%m-%d")).days} day(s) ago.',
                                                                       'Do you want to re-download the latest posts?'],
                                                      lambda: (self.confirm_frame.destroy(),
                                                               self.data_response.__setitem__(0, True),
                                                               threading.Thread(target=self.load_data).start()),
                                                      lambda: (self.confirm_frame.destroy(),
                                                               self.data_response.__setitem__(0, False),
                                                               threading.Thread(target=self.load_data).start()))
                        elif self.data_response[0]:
                            self.download_latest_posts(today, config['options']["blacklist"],
                                                       config['profile']['login'], config['options']["min_score"],
                                                       config['options']["default_rating"])
                            if self.data_state != 'error':
                                if not self.cancel_loading:
                                    self.data_state = 'rec'
                                self.data_response = [None]
                        else:
                            if self.data_state != 'error':
                                if not self.cancel_loading:
                                    self.data_state = 'rec'
                                self.data_response = [None]
                    else:
                        if self.data_response[0] == None:
                            write_to_log("Existing instance of latest posts was found.")
                            self.show_confirm_overlay("Latest posts", ["Latest posts might not have been updated yet.",
                                                                       'Do you want to re-download the latest posts?'],
                                                      lambda: (self.confirm_frame.destroy(),
                                                               self.data_response.__setitem__(0, True),
                                                               threading.Thread(target=self.load_data).start()),
                                                      lambda: (self.confirm_frame.destroy(),
                                                               self.data_response.__setitem__(0, False),
                                                               threading.Thread(target=self.load_data).start()))
                        elif self.data_response[0]:
                            self.download_latest_posts(today, config['options']["blacklist"],
                                                       config['profile']['login'], config['options']["min_score"],
                                                       config['options']["default_rating"])
                            if self.data_state != 'error':
                                if not self.cancel_loading:
                                    self.data_state = 'rec'
                                self.data_response = [None]
                        else:
                            if self.data_state != 'error':
                                if not self.cancel_loading:
                                    self.data_state = 'rec'
                                self.data_response = [None]
                else:
                    self.download_latest_posts(today, config['options']["blacklist"], config['profile']['login'],
                                               config['options']["min_score"], config['options']["default_rating"])
                    if self.data_state != 'error':
                        if not self.cancel_loading:
                            self.data_state = 'rec'
                        self.data_response = [None]
        # Run recommendation system
        if self.data_state == 'rec':
            self.cancel.config(state="disabled")
            self.recommendations(config['advanced']['threads'], config['advanced']["posts_per_thread"],
                                 config['advanced']["grading"])
            if self.data_state != 'error':
                self.data_state = 'start'
                self.data_response = [None]
                time.sleep(2)
                self.tk_images = []
                self.tk_images_data = []
                self.loading_state = 'loading'
                self.loading_frame.destroy()
                self.set_completed_state()
        # If cancel request was received
        if self.cancel_loading:
            self.log_to_console('Cancellation request detected.')
            write_to_log('Cancellation request detected.')
            if self.data_state != 'error':
                time.sleep(2)
            self.loading_frame.destroy()
            self.set_initial_state()
            self.data_state = 'start'
            self.data_response = [None]

    # A special loading overlay that is shown when loading any image without a need for a "console" window.
    def show_loading_images_overlay(self):
        self.loading_frame_img = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.loading_frame_img.place(relx=0.5, rely=0.5, anchor="center", width=400, height=75)

        title = tk.Label(self.loading_frame_img, text="Loading, please wait...", font=("Segoe UI", 12, "bold"),
                         bg=overlays_color, fg="white")
        title.pack(pady=5)

        self.progress_img = ttk.Progressbar(self.loading_frame_img, orient="horizontal", length=300, mode="determinate")
        self.progress_img.pack(pady=5)
        self.progress_img["value"] = 0

    # This function will initially load help images. Then it will attempt to load preview images of the results
    def load_images(self):
        # Loading help images, if they have not been already loaded before
        if not self.help_loaded:
            write_to_log('Loading help images...')
            for index, page in enumerate(self.help_pages):
                if page['additional_img']:
                    try:
                        self.help_pages[index]['additional_img']['img'] = ImageTk.PhotoImage(
                            Image.open(page['additional_img']['img']))
                    except:
                        self.help_pages[index]['additional_img'] = "Missing"
                self.progress_img["value"] = (index + 1) / (len(self.help_pages) + len(self.final_res)) * 100
            self.help_loaded = True
            write_to_log("Loading help images completed.")
        write_to_log('Loading results images...')
        failed_indexes = ''
        # Attemping to load preview images
        for index, data in enumerate(self.final_res.items()):
            try:
                id = data[0]
                url = data[1][0]
                per = data[1][1]
                ext = data[1][2]
                if is_base64(url):
                    img = Image.open(BytesIO(
                        base64.b64decode(url)))  # If the image is a base64 encoded image data, then just load that
                else:
                    try:
                        if ext.lower() == 'jpg' or ext.lower() == 'jpeg':
                            ext = 'jpeg'
                        img = Image.open(
                            f'data/placeholders/placeholder_{ext.lower()}.png')  # If it's not, then use a placeholder image that shows the file extension of the post
                    except:
                        img = Image.new(mode="RGB", size=(150, 150), color=(248, 247,
                                                                            247))  # If even the placeholder image cannot be loaded, then create just an empty rectangular square
                        failed_indexes += f'{index}, '
                img.thumbnail((150, 150))
                tk_img = ImageTk.PhotoImage(img)
                self.tk_images.append(tk_img)
                self.tk_images_data += [(id, url, per, ext)]
                self.progress_img["value"] = ((index + 1) / (len(self.help_pages) + len(self.final_res)) * 100) / 2
                self.loading_frame_img.update_idletasks()
            except Exception as e:
                write_to_log(f"Error loading image: {e}")
        if failed_indexes != '':
            write_to_log(f'{failed_indexes}- FAILED')
        else:
            write_to_log('Every image loaded successfully.')
        self.loading_state = 'complete'
        self.set_completed_state()
        write_to_log('Loading results images completed.')

    # Using images that were previously loaded, the program places them onto the scrollable area where everything will be displayed
    # special_case - is the case when a user clicks on the first "Show more images" label. This will display a warning message regarding the uncertainty of the next recommendations.
    def place_more_images(self, special_case=False):
        write_to_log('Placing images on main area...')
        try:
            self.load_more_label.destroy()  # Atttempting to remove that "Show more images" label, because it will be eventually placed below everything
        except:
            None
        for index in range(self.how_many_images_to_download * self.more_images,
                           self.how_many_images_to_download * (self.more_images + 1)):
            if index >= len(self.tk_images) - 1:
                self.load_images_limit = True
                break
            id = self.tk_images_data[index][0]
            per = self.tk_images_data[index][2]
            ext = self.tk_images_data[index][3]
            img_frame = tk.Frame(self.scrollable_frame, bg=scrollable_area_color)
            img_label = tk.Label(img_frame, image=self.tk_images[index], bg=scrollable_area_color)
            img_label.pack()
            # Creating a small text in the upper left corner of the image that shows if it's an animated or a video post
            if ext.lower() in ["gif", "apng", "webm", "mp4", "swf"]:
                ext_frame = tk.Frame(img_frame, bg=overlays_color, bd=2, relief="ridge")
                ext_frame.place(relx=0.1, rely=0.1, anchor="center", width=30, height=20)
                text_ext = tk.Label(ext_frame,
                                    text="WEBM" if ext.lower() == "webm" else "MP4" if ext.lower() == "mp4" else "SWF" if ext.lower() == "swf" else "ANIM",
                                    fg="white", bg=overlays_color, font=font.Font(family="Segoe UI", size=7))
                text_ext.pack()
            text_id = tk.Label(img_frame, text=f"#{id}", fg="white", bg=scrollable_area_color,
                               font=font.Font(family="Segoe UI", size=9, underline=True))
            text_id.pack()
            text_per = tk.Label(img_frame, text=f"{round(per * 100, 3)}%", fg="white", bg=scrollable_area_color,
                                font=font.Font(family="Segoe UI", size=9))
            text_per.pack()
            # When clicking on the id of the recommended post, a link to it will be automatically copied to user's clipboard
            text_id.bind("<Button-1>", lambda e, ent=text_id: (write_to_log(f'Copied the link successfully.'),
                                                               pyperclip.copy(
                                                                   f'https://e621.net/posts/{ent["text"][1:]}'),
                                                               threading.Thread(
                                                                   target=self.show_copy_overlay).start() if self.copy_state == 'nothing' else None))
            row = index // self.columns
            col = index % self.columns
            img_frame.grid(row=row, column=col, padx=10, pady=10)
            try:
                self.progress_img["value"] = ((index + 1) / self.how_many_images_to_download * 100) + (
                    0 if self.more_images >= 1 else 50)
                self.loading_frame_img.update_idletasks()
            except:
                None
        # Do not show the "Show more images" label if there is no recommendations left
        if not self.load_images_limit:
            label_frame = tk.Frame(self.scrollable_frame, bg=scrollable_area_color)
            self.load_more_label = tk.Label(label_frame, text="Show more images", fg="white", bg=scrollable_area_color,
                                            font=font.Font(family="Segoe UI", size=12, underline=True))
            self.load_more_label.pack()
            label_frame.grid(row=index // self.columns + 1, column=0)
            self.load_more_label.bind("<Button-1>", self.load_more_images_label)
        self.loading_frame_img.destroy()
        if not special_case:
            self.enable_sidebar()
            self.ability_to_exit = True
        write_to_log('Placing images completed.')

    # This is a warning message that I was talking about before. It will warn the user that the next images have less similarity percentage and they will not have preview images
    def show_warning_overlay(self):
        self.warning_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.warning_frame.place(relx=0.5, rely=0.5, anchor="center", width=400, height=200)

        title = tk.Label(self.warning_frame, text="Warning!", font=("Segoe UI", 12, "bold"), bg=overlays_color,
                         fg="white")
        title.pack(pady=7)
        tk.Label(self.warning_frame,
                 text="There is less confidence about recommending the next images.\nProceed with caution!",
                 font=("Segoe UI", 10), bg=overlays_color, fg="white").pack(pady=3)

        tk.Label(self.warning_frame,
                 text="Additionally they will not have a preview image\ndue to multiple reasons and limitations.",
                 font=("Segoe UI", 10), bg=overlays_color, fg="white").pack(pady=3)

        def okay_command():
            self.enable_sidebar()
            self.ability_to_exit = True
            self.warning_frame.destroy()

        ttk.Button(self.warning_frame, text="Okay", command=okay_command).pack(pady=5, padx=30)

    # Command for "Show more images" label
    def load_more_images_label(self, event):
        self.ability_to_exit = False
        write_to_log('Showing more of the results.')
        if not self.load_images_limit:
            self.more_images += 1
            self.show_loading_images_overlay()
            self.disable_sidebar(do_not_copy=True)
            if self.more_images == 1:
                self.show_warning_overlay()
                threading.Thread(target=self.place_more_images, args=(True,)).start()
            else:
                threading.Thread(target=self.place_more_images).start()

    # A small overlay shown at the bottom of the screen that tells the user that link was copied
    def copy_overlay(self):
        self.clipboard_frame = tk.Frame(self.main_area, bg=overlays_color, bd=2, relief="ridge")
        self.clipboard_frame.place(relx=0.5, rely=0.9, anchor="center", width=200, height=35)

        title = tk.Label(self.clipboard_frame, text="Copied the link to a clipboard.", font=("Segoe UI", 10, "bold"),
                         bg=overlays_color, fg="white")
        title.pack(pady=5)

    # The same story as show_exit_overlay
    # Needed only to change a value of a variable and making a delay
    def show_copy_overlay(self):
        self.copy_state = 'showing'
        self.copy_overlay()
        time.sleep(1)
        self.clipboard_frame.destroy()
        self.copy_state = 'nothing'

    # Completed state
    # When the results should be loaded and shown to the user
    def set_completed_state(self):
        write_to_log('Completed state.')
        self.current_state = 'completed'
        try:
            with open("csv_files/results/results.json") as f:
                self.final_res = json.load(f)
        except:
            self.final_res = {}
        # If there is no results, then set the state to initial
        if self.final_res == {}:
            write_to_log('No results were found.\nInitial state.')
            self.current_state = 'initial'
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            label = tk.Label(self.scrollable_frame, text="Nobody here but us chickens!", fg="white",
                             bg=scrollable_area_color, font=("Segoe UI", 14))
            label.pack(pady=20)
            self.enable_sidebar()
            self.ability_to_exit = True
            if not self.help_loaded:
                self.disable_sidebar()
                self.ability_to_exit = False
                self.show_loading_images_overlay()
                threading.Thread(target=self.load_images_help).start()

        else:
            # If the results exist, then firsly load them
            if self.loading_state != 'complete':
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()
                label = tk.Label(self.scrollable_frame, text="Nobody here but us chickens!", fg="white",
                                 bg=scrollable_area_color, font=("Segoe UI", 14))
                label.pack(pady=20)
                self.show_loading_images_overlay()
                threading.Thread(target=self.load_images).start()
            # And only then place them on the scrollable area
            else:
                self.more_images = 0
                self.load_images_limit = False
                self.canvas.yview_moveto(0)
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()
                threading.Thread(target=self.place_more_images).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
