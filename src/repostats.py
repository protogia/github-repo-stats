import os
import pandas as pd
import plotly.express as px
from github import Github, GithubException, Auth
from datetime import datetime, timedelta
from argparse import ArgumentParser
from rich_argparse import RichHelpFormatter
import repoconfig.config as repoconf

def save_plotly_json(fig, name):
    """Saves a plotly figure as a JSON file for your frontend."""
    if not os.path.exists(repoconf.PLOT_DIR):
        os.makedirs(repoconf.PLOT_DIR)
    path = os.path.join(repoconf.PLOT_DIR, f"{name}.json")
    fig.write_json(path)
    print(f"💾 JSON Exported: {path}")

def update_history(df_new, filename):
    """Merges new data with historical CSV to prevent 14-day data loss."""
    path = os.path.join(os.path.dirname(repoconf.HISTORY_DIR), filename)
    
    if os.path.exists(path) and not df_new.empty:
        df_old = pd.read_csv(path)
        # Combine, ensure dates are strings for comparison, and drop duplicates
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        # We unique-check by date and repo so we don't double-count the same day
        if 'date' in df_combined.columns:
            df_combined = df_combined.drop_duplicates(subset=['date', 'repo'], keep='last')
        df_combined.to_csv(path, index=False)
        return df_combined
    
    df_new.to_csv(path, index=False)
    return df_new

def fetch_from_github(exclude=True):
    """Fetch fresh data from GitHub API."""
    g = Github(auth=Auth.Token(repoconf.ACCESS_TOKEN))
    user = g.get_user()
    
    views_list, clones_list, refs_list, repo_stats = [], [], [], []
    lang_data = []
    
    today = datetime.now().date().isoformat()
    two_weeks_ago = datetime.now() - timedelta(days=14)
    excluded_names = getattr(repoconf, 'EXCLUDED_REPOS', []) if exclude else []

    for repo in user.get_repos():
        if repo.fork or (repo.name in excluded_names):
            continue
            
        try:
            print(f"📡 Fetching: {repo.name}...")
            
            # 1. Traffic (The 14-day window data)
            for day in repo.get_views_traffic().views:
                views_list.append({"date": day.timestamp.date().isoformat(), "repo": repo.name, "views": day.count})
            for day in repo.get_clones_traffic().clones:
                clones_list.append({"date": day.timestamp.date().isoformat(), "repo": repo.name, "clones": day.count})

            # 2. Referrers
            for r in repo.get_top_referrers():
                refs_list.append({"date": today, "repo": repo.name, "site": r.referrer, "views": r.count})

            # 3. Issues, PR Health, Activity
            open_prs = repo.get_pulls(state='open').totalCount
            closed_prs = repo.get_pulls(state='closed').totalCount
            recent_commits = repo.get_commits(since=two_weeks_ago).totalCount
            
            repo_stats.append({
                "repo": repo.name,
                "open_issues": repo.open_issues_count,
                "stars": repo.stargazers_count,
                "open_prs": open_prs,
                "closed_prs": closed_prs,
                "recent_activity": recent_commits
            })

            # 4. Languages
            for lang, bytes_val in repo.get_languages().items():
                lang_data.append({"repo": repo.name, "language": lang, "bytes": bytes_val})

        except GithubException:
            continue

    return {
        "views": pd.DataFrame(views_list),
        "clones": pd.DataFrame(clones_list),
        "referrers": pd.DataFrame(refs_list),
        "general": pd.DataFrame(repo_stats),
        "languages": pd.DataFrame(lang_data)
    }

def run_plots(data, args):
    """Generates JSON plots based on the active flags."""
    
    # Always plot General Health (Issues, PRs, Activity)
    if not data["general"].empty:
        df_g = data["general"]
        # PR Health
        fig_pr = px.bar(df_g, x="repo", y=["open_prs", "closed_prs"], title="PR Health", barmode="group", template="plotly_dark")
        save_plotly_json(fig_pr, "pr_health")
        # Issues & Activity
        fig_act = px.bar(df_g, x="repo", y=["open_issues", "recent_activity"], title="Issues vs Activity", template="plotly_dark")
        save_plotly_json(fig_act, "activity")

    # Always plot Language Composition
    if not data["languages"].empty:
        lang_sum = data["languages"].groupby("language")["bytes"].sum().reset_index()
        fig_lang = px.pie(lang_sum, values="bytes", names="language", title="Global Language Composition", template="plotly_dark")
        save_plotly_json(fig_lang, "languages")

    # Conditional Plots based on Flags
    if args.views and not data["views"].empty:
        fig_v = px.line(data["views"], x="date", y="views", color="repo", title="Long-term Views", template="plotly_dark")
        save_plotly_json(fig_v, "views")

    if args.clones and not data["clones"].empty:
        df_c = data["clones"].sort_values(["repo", "date"])
        df_c["cum_clones"] = df_c.groupby("repo")["clones"].cumsum()
        fig_c = px.line(df_c, x="date", y="cum_clones", color="repo", title="Cumulative Clones", template="plotly_dark")
        save_plotly_json(fig_c, "clones")

    if args.referrers and not data["referrers"].empty:
        ref_sum = data["referrers"].groupby("site")["views"].sum().sort_values(ascending=False).head(10).reset_index()
        fig_r = px.pie(ref_sum, values="views", names="site", title="Top Traffic Sources", template="plotly_dark")
        save_plotly_json(fig_r, "referrers")

if __name__ == "__main__":
    parser = ArgumentParser(description="GitHub Long-term Stats", formatter_class=RichHelpFormatter)
    parser.add_argument("--views", "-v", action="store_true", help="Plot viewer-stats.")    
    parser.add_argument("--clones", "-c", action="store_true", help="Plot cloning-stats.")    
    parser.add_argument("--referrers", "-r", action="store_true", help="Plot referrer-stats.")    
    parser.add_argument("--fetch", "-f", action="store_true", help="Fetch fresh data and update history.")
    args = parser.parse_args()

    if args.fetch:
        fresh_data = fetch_from_github()
        
        stats = {
            "views": update_history(fresh_data["views"], "hist_views.csv"),
            "clones": update_history(fresh_data["clones"], "hist_clones.csv"),
            "referrers": update_history(fresh_data["referrers"], "hist_refs.csv"),
            "general": update_history(fresh_data["general"], "hist_general.csv"),
            "languages": update_history(fresh_data["languages"], "hist_langs.csv")
        }
    else:
        try:
            stats = {
                "views": pd.read_csv(os.path.join(os.path.dirname(repoconf.HISTORY_DIR), "hist_views.csv")),
                "clones": pd.read_csv(os.path.join(os.path.dirname(repoconf.HISTORY_DIR), "hist_clones.csv")),
                # "referrers": pd.read_csv(os.path.join(os.path.dirname(repoconf.HISTORY_DIR), "hist_refs.csv")),
                "general": pd.read_csv(os.path.join(os.path.dirname(repoconf.HISTORY_DIR), "hist_general.csv")),
                "languages": pd.read_csv(os.path.join(os.path.dirname(repoconf.HISTORY_DIR), "hist_langs.csv"))
            }
        except FileNotFoundError:
            print("No historical data found. Run with --fetch first.")
            exit()

    run_plots(stats, args)