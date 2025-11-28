"""Enhanced PR Review Handler with Inline Comments

This module shows how to post detailed inline comments from specialized agents.
Add this to your orchestrator.py to replace the _handle_pr_review method.
"""

def _handle_pr_review_enhanced(self, input_data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """Handle GitHub Pull Request review with inline comments from specialized agents."""
    from ..github.client import GitHubClient
    
    repo_url = input_data.get("repo_url", "")
    pr_number = input_data.get("pr_number")
    post_comments = input_data.get("post_comments", False)
    post_inline = input_data.get("post_inline", True)  # NEW: inline comments
    
    if not repo_url or not pr_number:
        return {"status": "error", "error": "repo_url and pr_number are required"}
    
    logger.info(f"Reviewing PR #{pr_number} from {repo_url}")
   
    with GitHubClient() as github:
        # Get PR details
        pr = github.get_pull_request(repo_url, pr_number)
        
        results = {
            "status": "ok",
            "task_id": task_id,
            "pr": {
                "number": pr.number,
                "title": pr.title,
                "author": pr.author,
                "files_changed": len(pr.files)
            },
            "file_reviews": [],
            "inline_comments_posted": 0
        }
        
        all_inline_comments = []  # Collect all inline comments
        
        # Review each changed file
        for pr_file in pr.files:
            if pr_file.status == "removed":
                continue
            
            # Get full file content
            try:
                content = github.get_pr_file_content(repo_url, pr_number, pr_file.filename)
            except Exception as e:
                logger.warning(f"Could not get content for {pr_file.filename}: {e}")
                continue
            
            # Run analysis on the file
            file_review = {
                "filename": pr_file.filename,
                "status": pr_file.status,
                "additions": pr_file.additions,
                "deletions": pr_file.deletions
            }
            
            # Only analyze code files
            if self._is_code_file(pr_file.filename):
                logger.info(f"Analyzing {pr_file.filename}...")
                
                # Run all agents (now with specialized sub-agents!)
                analysis_result = self.agents["analysis"].process(content)
                bug_result = self.agents["bug_detection"].process(content)
                security_result = self.agents["security"].process(content)
                
                file_review["analysis"] = analysis_result
                file_review["bugs"] = bug_result
                file_review["security"] = security_result
                
                # Convert findings to inline comments
                if post_inline:
                    # Code review findings
                    for suggestion in analysis_result.get("suggestions", []):
                        if isinstance(suggestion, dict):  # New structured format
                            comment = self._finding_to_inline_comment(
                                suggestion, 
                                pr_file.filename,
                                "💡 Code Review"
                            )
                            if comment:
                                all_inline_comments.append(comment)
                    
                    # Bug findings
                    for bug in bug_result.get("bugs", []):
                        if isinstance(bug, dict):
                            comment = self._finding_to_inline_comment(
                                bug,
                                pr_file.filename,
                                "🐛 Bug"
                            )
                            if comment:
                                all_inline_comments.append(comment)
                    
                    # Security findings
                    for vuln in security_result.get("vulnerabilities", []):
                        if isinstance(vuln, dict):
                            comment = self._finding_to_inline_comment(
                                vuln,
                                pr_file.filename,
                                "🔒 Security"
                            )
                            if comment:
                                all_inline_comments.append(comment)
            
            results["file_reviews"].append(file_review)
        
        # Generate overall review summary
        summary = self._generate_enhanced_pr_summary(results["file_reviews"], all_inline_comments)
        results["summary"] = summary
        
        # Post review with inline comments
        if post_comments:
            try:
                if post_inline and all_inline_comments:
                    # Create a full review with inline comments
                    github.create_review(
                        repo_url,
                        pr_number,
                        body=summary,
                        event="COMMENT",
                        comments=all_inline_comments
                    )
                    results["inline_comments_posted"] = len(all_inline_comments)
                    logger.info(f"Posted review with {len(all_inline_comments)} inline comments")
                else:
                    # Just post summary comment
                    github.post_pr_comment(repo_url, pr_number, summary)
                    logger.info("Posted review summary comment")
                
                results["comment_posted"] = True
            except Exception as e:
                logger.error(f"Failed to post comments: {e}")
                results["comment_posted"] = False
                results["comment_error"] = str(e)
    
    return results


def _finding_to_inline_comment(
    self,
    finding: Dict[str, Any],
    file_path: str,
    icon: str
) -> Optional[Dict[str, Any]]:
    """Convert a Finding object to GitHub inline comment format.
    
    Args:
        finding: Finding dict with category, severity, description, etc.
        file_path: Path to the file
        icon: Emoji icon for comment type
        
    Returns:
        Inline comment dict for GitHub API, or None if no line number
    """
    # Extract line number from evidence or location
    line_number = None
    
    # Try evidence first (new format from specialized agents)
    if "evidence" in finding and isinstance(finding["evidence"], dict):
        line_number = finding["evidence"].get("line_number")
    
    # Fallback to parsing location string
    if not line_number and "location" in finding:
        location = finding.get("location", "")
        import re
        match = re.search(r'\d+', location)
        if match:
            line_number = int(match.group())
    
    if not line_number:
        return None  # Can't post inline comment without line number
    
    category = finding.get("category", "Issue")
    severity = finding.get("severity", "medium").capitalize()
    description = finding.get("description", "")
    fix = finding.get("fix_suggestion") or finding.get("fix") or finding.get("remediation", "")
    confidence = finding.get("confidence", 0.0)
    
    # Format comment body
    comment_body = f"{icon} **{category}** ({severity})\n\n"
    comment_body += f"{description}\n\n"
    
    if fix:
        comment_body += f"**Suggested Fix:**\n{fix}\n\n"
    
    # Add evidence code snippet if available
    if "evidence" in finding and "code_snippet" in finding["evidence"]:
        snippet = finding["evidence"]["code_snippet"]
        if snippet:
            comment_body += f"**Evidence:**\n```python\n{snippet}\n```\n\n"
    
    comment_body += f"*Confidence: {confidence:.0%}*"
    
    return {
        "path": file_path,
        "line": line_number,
        "body": comment_body
    }


def _generate_enhanced_pr_summary(
    self,
    file_reviews: List[Dict[str, Any]],
    inline_comments: List[Dict[str, Any]]
) -> str:
    """Generate enhanced PR summary with stats from specialized agents."""
    summary_parts = ["## 🤖 Multi-Agent Code Review (Specialized Agents)\\n"]
    
    # Count findings by category
    findings_by_category = {}
    findings_by_severity = {}
    
    for review in file_reviews:
        # Count code review suggestions
        if "analysis" in review:
            for suggestion in review["analysis"].get("suggestions", []):
                if isinstance(suggestion, dict):
                    cat = suggestion.get("category", "Code Review")
                    sev = suggestion.get("severity", "medium")
                    findings_by_category[cat] = findings_by_category.get(cat, 0) + 1
                    findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1
        
        # Count bugs
        if "bugs" in review:
            for bug in review["bugs"].get("bugs", []):
                if isinstance(bug, dict):
                    cat = bug.get("category", "Bug")
                    sev = bug.get("severity", "medium")
                    findings_by_category[cat] = findings_by_category.get(cat, 0) + 1
                    findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1
        
        # Count security issues
        if "security" in review:
            for vuln in review["security"].get("vulnerabilities", []):
                if isinstance(vuln, dict):
                    cat = vuln.get("category", "Security")
                    sev = vuln.get("severity", "medium")
                    findings_by_category[cat] = findings_by_category.get(cat, 0) + 1
                    findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1
    
    # Overview stats
    summary_parts.append(f"**Files Reviewed:** {len(file_reviews)}\\n")
    summary_parts.append(f"**Total Findings:** {sum(findings_by_category.values())}\\n")
    summary_parts.append(f"**Inline Comments:** {len(inline_comments)}\\n\\n")
    
    # Severity breakdown
    if findings_by_severity:
        summary_parts.append("### 📊 Findings by Severity\\n\\n")
        for sev in ["critical", "high", "medium", "low"]:
            if sev in findings_by_severity:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(sev, "⚪")
                summary_parts.append(f"{icon} **{sev.capitalize()}**: {findings_by_severity[sev]}\\n")
        summary_parts.append("\\n")
    
    # Category breakdown
    if findings_by_category:
        summary_parts.append("### 🏷️ Findings by Category\\n\\n")
        for cat, count in sorted(findings_by_category.items(), key=lambda x: x[1], reverse=True):
            summary_parts.append(f"- **{cat}**: {count}\\n")
        summary_parts.append("\\n")
    
    # Note about specialized agents
    summary_parts.append("### ⚡ Powered by Specialized Agents\\n\\n")
    summary_parts.append("This review was performed by **12 specialized sub-agents**:\\n")
    summary_parts.append("- 4 Code Review agents (Naming, Quality, Duplication, PEP8)\\n")
    summary_parts.append("- 4 Bug Detection agents (Logic, Edge Cases, Types, Runtime)\\n")
    summary_parts.append("- 4 Security agents (Injection, Auth, Data Exposure, Dependencies)\\n\\n")
    summary_parts.append("All findings filtered by confidence threshold and deduplicated.\\n\\n")
    
    summary_parts.append("---\\n*Generated by Multi-Agent Code Review System v2.0*")
    
    return "".join(summary_parts)
