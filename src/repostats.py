import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from github import Github, GithubException, Auth
from datetime import datetime, timedelta
from argparse import ArgumentParser
from rich_argparse import RichHelpFormatter
import repoconfig.config as repoconf

LABEL_COLORS = {
    'bug': '#d62728',           # red
    'documentation': '#1f77b4', # blue
    'enhancement': "#b3f0ff",   # light blue 
    'help wanted': "#068B0D",   # green
    'good first issue': "#863DC2", # purple
    'question': '#e377c2',      # pink
    'wontfix': '#ffffff',       # white
    'duplicate': '#7f7f7f',     # grey
    'unlabeled': '#000000'      # black
}


def save_plotly_json(fig, name):
    if not os.path.exists(repoconf.PLOT_DIR):
        os.makedirs(repoconf.PLOT_DIR)
    path = os.path.join(repoconf.PLOT_DIR, f"{name}.json")
    fig.write_json(path)
    print(f"💾 JSON Exported: {path}")


def safe_read_csv(path):
    try:
        df = pd.read_csv(path)
        return df if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def update_history(df_new, filename, subset=['date', 'repo']):
    path = os.path.join(os.path.dirname(repoconf.HISTORY_DIR), filename)
    df_old = safe_read_csv(path)
    
    if df_new.empty:
        return df_old

    df_combined = pd.concat([df_old, df_new], ignore_index=True)
    
    actual_subset = [c for c in subset if c in df_combined.columns]
    df_combined = df_combined.drop_duplicates(subset=actual_subset, keep='last')
    
    sort_cols = [c for c in ['date', 'repo'] if c in df_combined.columns]
    if sort_cols:
        df_combined = df_combined.sort_values(sort_cols)
        
    df_combined.to_csv(path, index=False)
    return df_combined


def fetch_from_github(args, exclude=True):
    g = Github(auth=Auth.Token(repoconf.ACCESS_TOKEN))
    user = g.get_user()

    commit_list, views_list, clones_list, refs_list = [], [], [], []
    repo_general_list, labels_list = [], []

    since = datetime.now() - timedelta(days=14)
    excluded_names = getattr(repoconf, 'EXCLUDED_REPOS', []) if exclude else []

    for repo in user.get_repos():
        if repo.fork or repo.name in excluded_names:
            continue

        try:
            print(f"Fetching: {repo.name}...")

            if args.labels:
                issues = repo.get_issues(state='open')
                for issue in issues:
                    labels = issue.get_labels()
                    if labels.totalCount == 0:
                        labels_list.append({
                            "repo": repo.name, 
                            "label": "unlabeled", 
                            "issue_nr": issue.number
                        })
                    else:
                        for label in labels:
                            labels_list.append({
                                "repo": repo.name, 
                                "label": label.name.lower(), 
                                "issue_nr": issue.number
                            })

            if args.commits:
                commits = repo.get_commits(since=since)
                commits_by_date = {}
                for c in commits:
                    commit_date = c.commit.committer.date.date().isoformat()
                    commits_by_date[commit_date] = commits_by_date.get(commit_date, 0) + 1
                
                for date, count in commits_by_date.items():
                    commit_list.append({"date": date, "repo": repo.name, "commits": count})

            if args.views:
                for day in repo.get_views_traffic().views:
                    views_list.append({"date": day.timestamp.date().isoformat(), "repo": repo.name, "views": day.count})

            if args.clones:
                for day in repo.get_clones_traffic().clones:
                    clones_list.append({"date": day.timestamp.date().isoformat(), "repo": repo.name, "clones": day.count})

            if args.referrers:
                today = datetime.now().date().isoformat()
                for r in repo.get_top_referrers():
                    refs_list.append({"date": today, "repo": repo.name, "site": r.referrer, "views": r.count})

            if args.general:
                repo_general_list.append({
                    "repo": repo.name,
                    "open_issues": repo.open_issues_count,
                    "stars": repo.stargazers_count,
                    "open_prs": len(list(repo.get_pulls(state='open'))),
                    "closed_prs": len(list(repo.get_pulls(state='closed'))),
                    "recent_activity": sum(1 for _ in repo.get_commits(since=since)),
                    "date": datetime.now().date().isoformat()
                })

        except GithubException as e:
            print(f"Error fetching {repo.name}: {e}")
            continue

    return {
        "commits": pd.DataFrame(commit_list),
        "views": pd.DataFrame(views_list),
        "clones": pd.DataFrame(clones_list),
        "referrers": pd.DataFrame(refs_list),
        "general": pd.DataFrame(repo_general_list),
        "labels": pd.DataFrame(labels_list)
    }


def plot_issue_labels_treemap(df):
    """Treemap of issue labels across repositories"""
    if df.empty:
        return None
    
    df_counts = df.groupby(['repo', 'label']).size().reset_index(name='count')
    
    fig = px.treemap(
        df_counts,
        path=[px.Constant("Repositories"), 'repo', 'label'],
        values='count',
        color='label',
        color_discrete_map=LABEL_COLORS,
        title="Type distribution of open issues per repository"
    )
    
    fig.update_traces(textinfo="label+value")
    fig.update_layout(margin=dict(t=50, l=10, r=10, b=10))
    return fig


def plot_issue_pr_distribution(df):
    """Stacked bar chart comparing issue and PR status"""
    if df.empty or not {'repo', 'open_issues', 'open_prs', 'closed_prs'}.issubset(df.columns):
        return None
    
    df_plot = df[['repo', 'open_issues', 'open_prs', 'closed_prs']].copy()
    df_plot = df_plot.sort_values('open_issues', ascending=False)
    
    fig = go.Figure(
        data=[
            go.Bar(name='Open Issues', x=df_plot['repo'], y=df_plot['open_issues'], marker_color='#EF553B'),
            go.Bar(name='Open PRs', x=df_plot['repo'], y=df_plot['open_prs'], marker_color='#00CC96'),
            go.Bar(name='Closed PRs', x=df_plot['repo'], y=df_plot['closed_prs'], marker_color='#636EFA'),
        ]
    )
    
    fig.update_layout(
        barmode='stack',
        title="Issues & Pull Requests by Repository",
        xaxis_title="Repository",
        yaxis_title="Count",
        hovermode='x unified',
        height=500
    )
    
    return fig


def plot_engagement_scatter(df):
    """Scatter plot: stars vs recent activity with size encoding"""
    if df.empty or not {'repo', 'stars', 'recent_activity', 'open_issues'}.issubset(df.columns):
        return None
    
    fig = px.scatter(
        df,
        x='stars',
        y='recent_activity',
        size='open_issues',
        color='open_issues',
        hover_name='repo',
        title="Repository Engagement: Stars vs Activity",
        labels={
            'stars': 'GitHub Stars',
            'recent_activity': 'Commits',
            'open_issues': 'Open Issues'
        },
        color_continuous_scale='Viridis'
    )
    
    fig.update_traces(
        hovertemplate='<b>%{hovertext}</b><br>Stars: %{x}<br>Activity: %{y}<br>Issues: %{marker.size}<extra></extra>'
    )
    
    return fig


def run_plots(data, args):
    if args.commits and not data["commits"].empty:
        df = data["commits"].copy()
        if {'date', 'repo', 'commits'}.issubset(df.columns):
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df_grouped = df.groupby(["date", "repo"])["commits"].sum().reset_index()

            totals = df_grouped.groupby("date")["commits"].sum().reset_index().rename(columns={"commits": "total_commits"})
            df_merged = df_grouped.merge(totals, on="date")

            fig = px.area(
                df_merged,
                x="date",
                y="commits",
                color="repo",
                groupnorm='percent',
                title="Commit Distribution (Relative %)"
            )

            fig.update_traces(
                hovertemplate=(
                    "Repo: %{fullData.name}<br>"
                    "Date: %{x}<br>"
                    "Commits: %{customdata[0]}<br>"
                    "Share: %{y:.2f}%<extra></extra>"
                ),
                customdata=df_merged[["commits"]].values
            )

            fig.update_layout(xaxis=dict(rangeslider=dict(visible=True), type="date"))
            save_plotly_json(fig, "commit_distribution")

    if args.views and not data.get("views", pd.DataFrame()).empty:
        df = data["views"]
        if {'date', 'views', 'repo'}.issubset(df.columns):
            fig_v = px.line(df, x="date", y="views", color="repo", title="Views")
            save_plotly_json(fig_v, "views")

    if args.clones and not data.get("clones", pd.DataFrame()).empty:
        df = data["clones"]
        if {'date', 'clones', 'repo'}.issubset(df.columns):
            df = df.sort_values(["repo", "date"])
            df["cum_clones"] = df.groupby("repo")["clones"].cumsum()
            fig_c = px.line(df, x="date", y="cum_clones", color="repo", title="Cumulative Clones")
            save_plotly_json(fig_c, "clones")

    if args.referrers and not data.get("referrers", pd.DataFrame()).empty:
        df = data["referrers"]
        if {'site', 'views'}.issubset(df.columns):
            ref_sum = df.groupby("site")["views"].sum().sort_values(ascending=False).head(10).reset_index()
            fig_r = px.pie(ref_sum, values="views", names="site", title="Top Traffic Sources")
            save_plotly_json(fig_r, "referrers")

    if args.general and not data.get("general", pd.DataFrame()).empty:
        df = data["general"]
        if {'repo', 'open_issues', 'stars'}.issubset(df.columns):
            fig_ip = plot_issue_pr_distribution(df)
            if fig_ip:
                save_plotly_json(fig_ip, "issue_pr_distribution")

            fig_sc = plot_engagement_scatter(df)
            if fig_sc:
                save_plotly_json(fig_sc, "engagement_scatter")

    if args.labels and not data.get("labels", pd.DataFrame()).empty:
        fig_tr = plot_issue_labels_treemap(data["labels"])
        if fig_tr:
            save_plotly_json(fig_tr, "labels_treemap")


if __name__ == "__main__":
    parser = ArgumentParser(description="GitHub Long-term Stats", formatter_class=RichHelpFormatter)
    parser.add_argument("--commits", "-m", action="store_true", help="Fetch and plot commit history")
    parser.add_argument("--views", "-v", action="store_true", help="Fetch and plot views")
    parser.add_argument("--clones", "-c", action="store_true", help="Fetch and plot clones")
    parser.add_argument("--referrers", "-r", action="store_true", help="Fetch and plot traffic sources")
    parser.add_argument("--general", "-g", action="store_true", help="Fetch general stats (Stars/PRs)")
    parser.add_argument("--labels", "-l", action="store_true", help="Fetch issue labels and create treemap")
    parser.add_argument("--fetch", "-F", action="store_true", help="Fetch fresh data from GitHub")
    args = parser.parse_args()

    filenames = {
        "commits": "hist_commits.csv",
        "views": "hist_views.csv",
        "clones": "hist_clones.csv",
        "referrers": "hist_refs.csv",
        "general": "hist_general.csv",
        "labels": "hist_labels.csv"
    }

    stats = {}

    if args.fetch:
        fresh_data = fetch_from_github(args)
        for key, fname in filenames.items():
            if getattr(args, key):
                dup_subset = ['repo', 'label', 'issue_nr'] if key == 'labels' else ['date', 'repo']
                stats[key] = update_history(fresh_data[key], fname, subset=dup_subset)
    else:
        for key, fname in filenames.items():
            if getattr(args, key):
                path = os.path.join(os.path.dirname(repoconf.HISTORY_DIR), fname)
                stats[key] = safe_read_csv(path)

    run_plots(stats, args)