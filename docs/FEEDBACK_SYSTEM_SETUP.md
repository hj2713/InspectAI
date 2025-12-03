# Feedback System Setup Guide

This guide will walk you through setting up the customer feedback loop using Supabase.

## 📋 Prerequisites

- Supabase account (free tier is fine)
- OpenAI API key (for generating embeddings)
- Your InspectAI deployment already working

## 🚀 Step-by-Step Setup

### 1. Run SQL Schema in Supabase

1. Go to your Supabase project: https://qwwvadfeyhlzjzjpvnto.supabase.co
2. Click "SQL Editor" in the left sidebar
3. Click "New Query"
4. Copy the entire contents of `supabase_schema.sql` file
5. Paste it into the SQL editor
6. Click "Run" (or press Cmd/Ctrl + Enter)

You should see success messages for:
- ✅ Extension created (vector)
- ✅ 3 tables created (review_comments, comment_feedback, feedback_filter_stats)
- ✅ Indexes created
- ✅ 2 functions created (match_similar_comments, get_comment_feedback_summary)

### 2. Verify pgvector Extension

1. In Supabase, go to "Database" → "Extensions"
2. Search for "vector"
3. Make sure it's **enabled** (toggle should be ON)

### 3. Add Environment Variables

Add these to your `.env` file:

```env
# Supabase
SUPABASE_URL=https://qwwvadfeyhlzjzjpvnto.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF3d3ZhZGZleWhsemp6anB2bnRvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQ3MzczMTAsImV4cCI6MjA4MDMxMzMxMH0.unf-RW9NHR5SuaRbxq5V88LN1LvhY7lASPNJ8Iainn4

# OpenAI (for embeddings only)
OPENAI_API_KEY=your_openai_api_key_here
```

**Important:** Even if you use Gemini/Bytez for the main LLM, you need OpenAI for embeddings because `text-embedding-ada-002` is the industry standard.

### 4. Deploy to Render

1. Add the environment variables in your Render dashboard:
   - Go to your app → "Environment" tab
   - Add `SUPABASE_URL`
   - Add `SUPABASE_KEY`
   - Add `OPENAI_API_KEY` (if not already there)

2. Redeploy:
   ```bash
   git add -A
   git commit -m "Add feedback system with Supabase"
   git push origin main
   ```

Render will auto-deploy.

### 5. Test It Out

1. Create a test PR in your repository
2. Comment `/inspectai_review`
3. Check Supabase:
   - Go to "Table Editor" → "review_comments"
   - You should see your posted comments!

4. Add a reaction to one of InspectAI's comments:
   - 👍 Thumbs up
   - 👎 Thumbs down

5. Wait 5 minutes for the sync job, or trigger another review
6. Check "comment_feedback" table - you should see the reaction!

## 🎯 How It Works

### When You Review a PR:

1. **Agent generates comments** → List of findings
2. **Feedback filter runs** → Checks for similar past comments
3. **Smart decisions:**
   - If similar comments were downvoted (👎) → **Skip this comment**
   - If similar comments were upvoted (👍) → **Boost confidence**
4. **Post filtered comments** to GitHub
5. **Store in Supabase** with embeddings for future learning

### Background Sync (Every 5 Minutes):

1. Fetch reactions from GitHub for recent comments
2. Store reactions in Supabase `comment_feedback` table
3. Next review uses this feedback data automatically!

## 📊 Monitoring & Analytics

### View Feedback Stats

```sql
-- See all comments with their feedback
SELECT 
    rc.comment_body,
    rc.category,
    rc.severity,
    COUNT(CASE WHEN cf.reaction_type = 'thumbs_up' THEN 1 END) as upvotes,
    COUNT(CASE WHEN cf.reaction_type = 'thumbs_down' THEN 1 END) as downvotes
FROM review_comments rc
LEFT JOIN comment_feedback cf ON rc.id = cf.comment_id
GROUP BY rc.id, rc.comment_body, rc.category, rc.severity
ORDER BY downvotes DESC;
```

### View Filter Effectiveness

```sql
-- See how many comments were filtered
SELECT 
    repo_full_name,
    SUM(total_comments_generated) as total_generated,
    SUM(comments_filtered_by_feedback) as filtered,
    SUM(comments_boosted_by_feedback) as boosted,
    ROUND(100.0 * SUM(comments_filtered_by_feedback) / SUM(total_comments_generated), 2) as filter_percentage
FROM feedback_filter_stats
GROUP BY repo_full_name;
```

### Find Most Downvoted Comment Types

```sql
-- Identify patterns in bad comments
SELECT 
    category,
    COUNT(DISTINCT rc.id) as comment_count,
    COUNT(CASE WHEN cf.reaction_type = 'thumbs_down' THEN 1 END) as downvotes
FROM review_comments rc
JOIN comment_feedback cf ON rc.id = cf.comment_id
WHERE cf.reaction_type = 'thumbs_down'
GROUP BY category
ORDER BY downvotes DESC;
```

## 🔧 Troubleshooting

### "Feedback system disabled" in logs

**Cause:** Missing `SUPABASE_URL` or `SUPABASE_KEY`

**Fix:** Add environment variables and redeploy

### "Error generating embedding"

**Cause:** Missing or invalid `OPENAI_API_KEY`

**Fix:** 
1. Get API key from https://platform.openai.com/api-keys
2. Add to environment variables
3. Restart server

### No reactions syncing

**Cause:** GitHub API rate limits or missing permissions

**Fix:**
1. Check GitHub App has "Pull requests: Read & write" permission
2. Check Render logs for errors
3. Sync happens every 5 minutes, be patient

### Comments not being filtered

**Cause:** Need more historical data (cold start problem)

**Fix:** 
- Feedback filtering requires at least 2-3 similar comments with reactions
- After 10-20 PRs reviewed, you'll start seeing filtering effects
- Be patient, it gets better over time!

## 🎓 Advanced: Custom Filtering Logic

You can modify the filtering logic in `src/feedback/feedback_system.py`:

```python
# Current logic (line ~200)
if total_negative > total_positive and total_negative >= 2:
    # Filter comment
    
# Example: More aggressive filtering
if total_negative >= 1:
    # Filter even with just 1 downvote
    
# Example: Only filter if severely downvoted
if total_negative > total_positive * 2:
    # Need 2x more downvotes than upvotes to filter
```

## 📈 Expected Impact

After 50-100 PRs reviewed with feedback:

- **30-50% reduction** in false positives
- **20-30% fewer** comments posted (better signal-to-noise)
- **10-15% higher** user satisfaction (fewer "not helpful" reactions)
- **Repo-specific learning** (style preferences per repo)

## 🚀 Next Steps

1. **Collect Feedback:** Ask users to react to comments
2. **Monitor Stats:** Check Supabase weekly
3. **Tune Thresholds:** Adjust similarity threshold (currently 0.85)
4. **Add Explanations:** Parse user comment replies for richer feedback

---

**Questions?** Open an issue or check the logs in Render dashboard.
