# github-repo-stats

Simple automation to fetch repository-statistics from github, save them locally and plot them.

You need a fine grained access token for github.
Go to settings -> developer settings -> secrets -> fine-grained-token.

It needs this permissions:
- administration: read-only
- content: read-only
- issues: read-only
- metadata: read-only


## install locally
```bash
git clone https://github.com/protogia/github-repo-stats.git
cd github-repo-stats
poetry install 

cp .env.template .env
# add github-token to .env
# GITHUB_ACCESS_TOKEN=
```

## run/test locally
```bash
poetry run python src/repostats.py --help 

poetry run python src/repostats.py -c -v -g -r -l -F # fetch all data from github, update hist_*.csv-files, plot data via plotly and save as .json
```

## view statistics
Run a webserver and check the index.html. Its a static collection of all plots.  