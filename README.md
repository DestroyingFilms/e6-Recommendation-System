# e6 Recommendation System
(I am bad at naming things)

![main](https://github.com/user-attachments/assets/b272795e-5376-48ee-8059-c9288a5135bb)

Welcome to this simple, yet quite effective recommendation program for e621! By analyzing your favorited posts, the algorithm will recommend you new ones that you will probably like.

## Warning

**!!THIS APPLICATION IS STRICTLY FOR ADULTS ONLY!!**

Every media content seen in the app itself is received and downloaded from [e621](https://e621.net/) using their [API service](https://e621.net/help/api). To follow the guidelines of the API documentation, an intentional delay of one second is implemented after every request.

Content that is commonly considered objectionable is blacklisted by default, some of which are ALWAYS blacklisted. Additionally, the default post rating is set to "Safe", which will only use "Safe" recent posts for recommendations.

Information such as options (config.json) and logs (log-YYYY-DD-MM-HH-MM-SS.log or latest.log) are kept as local files. API key is hidden and is kept only in the encrypted form in the OS itself using keyring backend.

## Basics

Everything needed for a proper e6 recommendation system is packaged here. It works by using a simple instruction:
1. Request profile (username, API key)
2. Read and use settings (blacklist, default post rating, etc.)
3. Download favorited & latest posts
4. Compare and give grades to all the latest posts with favorite ones

And that's it! After that you have your recommendations.

Well of course there is more steps that the program takes before that. So I will attempt to explain some of which might be necessary for understanding how this application operates.

If needed, all the information is available in the "Help" section in the app itself.

## Profile

![profile](https://github.com/user-attachments/assets/5d36070c-8dd9-4cf3-9081-e3f930a88ddc)

A profile or an account is the main source of data needed to figure out what should be recommended to you.

It is just your e621 account, but instead of using your password, you should use your [API key](https://e621.net/help/api) (can be created in the settings of your account on e621). It is needed because the app uses their API service to make requests to e6.

But as it is stated in the image, the API key is optional as long as your favorites are available to the public. Otherwise, if you have hidden your favorites, then the API key must be inputted into your profile.

Your account should also contain at least one favorited post. Without it, the recommendation will have nothing to work with and refuse to operate.

## Options/Settings

![options](https://github.com/user-attachments/assets/da2cecf6-d2e5-4090-a0d6-39066ce0c28a)

After successfully logging into your account you now have a lot of configurations available to you in the "Options":

- Profile - Change your current account.
- Blacklist - Set certain tags which will not be recommended to you. (OBJECTIONABLE TAGS/POSTS ARE BLACKLISTED BY DEFAULT)
- Minimum score threshold - Posts which have a lower score than the one set here will not be recommended.
- Default post rating - Posts which have a different rating than the one set here will not be recommended.
- Auto load results - Automatic process to load your recommendations, with their preview images, IDs and percentage grades, upon launch.
- Logging (Debug) - Will create log files, needed for debugging issues and problems.

### Advanced options

![advanced_options](https://github.com/user-attachments/assets/d6989ee0-8afe-40fd-92b7-a647a4ec85b7)

These last options are found in the "advanced" section, and require a bit more explanation than others:

- Number of threads

The algorithm works by using parallel threads to create seperate processes for each to analyze and grade smaller groups of posts. The bigger the number of threads is, the faster the algorithm, but this requires the CPU to create more threads.

- Posts per thread

These "smaller groups of posts" are created from all the recent posts. The size of each group is defined here. The same logic applies, the bigger the number, the faster the algorithm, with additional CPU and RAM usage. However, this parameter is the one which really influence the speed of the whole process.

- Grading method

The system compares each of the latest posts to all of your favorites and gives feedback on how similar they are. But each of that post will have a similarity percentage with every favorited ones. Let's say you have 100+ posts that you've favorited, so one latest post will have 100+ grades. To give a definitive similarity percentage to that one post we must use some kind of method, which is "MAX" and "AVG" here.
    
**Max**: Gets the maximum similarity with favorites. For instance, latest post is 20% similar to one of your favorites, but 90% to another. The grade for that post will be 90%.

**Avg**: Calculates and average match with all of your favorites. In the case presented above, the grade for the post will be (90+20)/2 % = 55%.

Both of these methods works in their own way, and it might be best to experiment with both of them before finding what suits you the most.

## Downloading fav/lat posts

![downloading](https://github.com/user-attachments/assets/6908fbcc-d542-47ec-9a4a-41c24bf08851)

Unfortunately, the application does not have direct access to all the posts from e621, and can only access them using their API service, that, of course, has its limits.

So, before even starting the algorithm, the program will download necessary posts. This does not mean that it will download full original images, videos or something like that. It will only get IDs and tags for favorited posts, and additional info on file extension and url of preview images for recent posts.

Later in the process, the program WILL download preview images of top results and encode them using base64. This is used to show the previews of the recommended posts to user. As of right now, only 30 previews will be downloaded, due to multiple reasons and limilations.

## Recommendation

![recommendation](https://github.com/user-attachments/assets/9cef0866-a830-4402-accc-ba1c10350ae1)

The algorithm itself is a cosine similarity function. It is a common method of creating simple recommendation systems in many areas. It works with additional help from CountVectorizer function that converts string data to numeric values.

Most of the time, the process will not take a long time, but it is depended on amount of posts used and PC specs.

After that, the results will be saved locally with encoded preview images located in there.


## TODO list (maybe)

While not being a part of the application itself, it is still an information that I want to keep at least for myself to remember.

Not every needed or wanted feature was implemented here yet, but I don't gurantee that I will eventually, as it is not a commercial product. I will maybe try to code some of them at least.

- Advanced blacklist
  - Or ~
  - Negation -
  - Groups ()
  - Wildcard *
- Options to choose other booru sites
  - Danbooru
  - Rule34
  - others...
- More settings/options
  - How many previews to download
  - Resizable window
  - Change layout/design

## Installation

The application was developed on Python 3.10 and Windows 11, any other version of Python or OS was not tested whatsoever.

Clone the repository from git clone: [https://github.com/DestroyingFilms/e6-Recommendation-System](https://github.com/DestroyingFilms/e6-Recommendation-System).

Go to the /e6_recommendation_system and install requirements using pip:

```bash
pip install -r requirements.txt
```

## Usage:

Run the GUI using a simple command:

```bash
python main.py
```

## Notes

This application was developed for myself personally as a hobby, and I don't think I've tested it enough or even properly for everyone to use.

I am open to criticism, but I don't think I will regularly fix issues. I will only check and try to solve them once I have time. So please don't expect much.

I hope you will still try it out and get some usage out of this project. Thanks in advance.

Created by DestroyingFilms.

## License:

[Apache license 2.0](https://github.com/DestroyingFilms/e6-Recommendation-System/blob/main/LICENSE)
