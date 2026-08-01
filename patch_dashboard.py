import sys

with open("envfix-dashboard/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# 1. Update auth modal to add Org View toggle
old_auth = """    <div id="auth-modal">
        <div class="modal-content glass">
            <h2>Connect Dashboard</h2>
            <p>Enter your team details to view envfix analytics.</p>
            
            <div class="input-group">
                <label>Team ID</label>
                <input type="text" id="teamIdInput" placeholder="e.g. 1" />
            </div>
            <div class="input-group">
                <label>API Key</label>
                <input type="password" id="apiKeyInput" placeholder="8d6bc28c-..." />
            </div>
            
            <button class="btn-primary" onclick="saveAuthAndLoad()">View Dashboard</button>
        </div>
    </div>"""

new_auth = """    <div id="auth-modal">
        <div class="modal-content glass">
            <h2>Connect Dashboard</h2>
            <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                <button id="tab-team" class="btn-primary" style="flex:1;" onclick="setMode('team')">Team View</button>
                <button id="tab-org" class="btn-primary" style="flex:1; background: transparent; border: 1px solid var(--card-border);" onclick="setMode('org')">Org View</button>
            </div>
            
            <div id="auth-team-fields">
                <p>Enter your team details.</p>
                <div class="input-group">
                    <label>Team ID</label>
                    <input type="text" id="teamIdInput" placeholder="e.g. 1" />
                </div>
                <div class="input-group">
                    <label>Team API Key</label>
                    <input type="password" id="apiKeyInput" placeholder="8d6bc28c-..." />
                </div>
            </div>

            <div id="auth-org-fields" style="display: none;">
                <p>Enter your organization details.</p>
                <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 1rem;">
                    Enterprise View is read-only, aggregate-only, and privacy-preserving. No individual developers are tracked.
                </p>
                <div class="input-group">
                    <label>Org ID</label>
                    <input type="text" id="orgIdInput" placeholder="e.g. 1" />
                </div>
                <div class="input-group">
                    <label>Admin API Key</label>
                    <input type="password" id="orgApiKeyInput" placeholder="admin-key-..." />
                </div>
            </div>
            
            <button class="btn-primary" onclick="saveAuthAndLoad()">View Dashboard</button>
        </div>
    </div>
    
    <script>
    let authMode = 'team';
    function setMode(mode) {
        authMode = mode;
        if (mode === 'team') {
            document.getElementById('tab-team').style.background = 'var(--accent-gradient)';
            document.getElementById('tab-org').style.background = 'transparent';
            document.getElementById('auth-team-fields').style.display = 'block';
            document.getElementById('auth-org-fields').style.display = 'none';
        } else {
            document.getElementById('tab-org').style.background = 'var(--accent-gradient)';
            document.getElementById('tab-team').style.background = 'transparent';
            document.getElementById('auth-team-fields').style.display = 'none';
            document.getElementById('auth-org-fields').style.display = 'block';
        }
    }
    </script>
"""

html = html.replace(old_auth, new_auth)

# 2. Add #org-dashboard-content below #dashboard-content
dashboard_end = """            </div>
        </div>
    </div>"""
    
new_org_dashboard = """
        <!-- Org Dashboard Content -->
        <div id="org-dashboard-content" style="display: none;">
            <div class="savings-section glass" style="margin-bottom: 2rem;">
                <div class="savings-grid">
                    <div class="savings-metric">
                        <h3>Estimated Org-wide Dollars Saved</h3>
                        <p id="org-val-dollars">$0</p>
                    </div>
                    <div class="savings-metric">
                        <h3>Estimated Org-wide Hours Saved</h3>
                        <p id="org-val-hours">0</p>
                    </div>
                </div>
            </div>

            <div class="metrics-grid">
                <div class="metric-card glass">
                    <div class="metric-title">Total Developers/Machines Reporting</div>
                    <div class="metric-value" id="org-val-machines">0</div>
                </div>
                <div class="metric-card glass">
                    <div class="metric-title">Redacted Secrets Count</div>
                    <div class="metric-value" id="org-val-secrets" style="color: var(--danger);">0</div>
                </div>
            </div>
            
            <div class="accuracy-section glass" style="margin-top: 2rem;">
                <h3>Proactive Environment Health (Doctor Scans)</h3>
                <div id="org-doctor-health" style="margin-top: 1rem; color: var(--text-muted);">
                    <!-- Populated by JS -->
                </div>
            </div>

            <div class="chart-section glass" style="margin-top: 2rem;">
                <h3>Team Breakdown</h3>
                <table style="width: 100%; text-align: left; margin-top: 1rem; border-collapse: collapse;">
                    <thead>
                        <tr style="border-bottom: 1px solid var(--card-border);">
                            <th style="padding: 10px;">Team ID</th>
                            <th style="padding: 10px;">Name</th>
                            <th style="padding: 10px;">Total Events</th>
                            <th style="padding: 10px;">Success Rate</th>
                            <th style="padding: 10px;">Dollars Saved</th>
                        </tr>
                    </thead>
                    <tbody id="org-team-breakdown">
                        <!-- Populated by JS -->
                    </tbody>
                </table>
            </div>
        </div>
"""

# Insert org dashboard right before the closing </div> of container
html = html.replace('        </div>\n    </div>\n\n    <script>', '        </div>\n' + new_org_dashboard + '\n    </div>\n\n    <script>')

# 3. Update JS Logic
old_js_start = """        // --- Auth Logic ---
        function openAuthModal() {
            document.getElementById('auth-modal').classList.add('active');
        }

        function saveAuthAndLoad() {
            const tId = document.getElementById('teamIdInput').value;
            const key = document.getElementById('apiKeyInput').value;
            if(!tId || !key) return;
            
            localStorage.setItem('envfix_team_id', tId);
            localStorage.setItem('envfix_api_key', key);
            
            document.getElementById('auth-modal').classList.remove('active');
            fetchDashboardData();
        }

        // Check auth on load
        window.addEventListener('DOMContentLoaded', () => {
            const tId = localStorage.getItem('envfix_team_id');
            const key = localStorage.getItem('envfix_api_key');
            if(tId && key) {
                document.getElementById('teamIdInput').value = tId;
                document.getElementById('apiKeyInput').value = key;
                fetchDashboardData();
            } else {
                openAuthModal();
            }
        });"""

new_js_start = """        // --- Auth Logic ---
        function openAuthModal() {
            document.getElementById('auth-modal').classList.add('active');
        }

        function saveAuthAndLoad() {
            if (authMode === 'team') {
                const tId = document.getElementById('teamIdInput').value;
                const key = document.getElementById('apiKeyInput').value;
                if(!tId || !key) return;
                
                localStorage.setItem('envfix_mode', 'team');
                localStorage.setItem('envfix_team_id', tId);
                localStorage.setItem('envfix_api_key', key);
            } else {
                const oId = document.getElementById('orgIdInput').value;
                const key = document.getElementById('orgApiKeyInput').value;
                if(!oId || !key) return;
                
                localStorage.setItem('envfix_mode', 'org');
                localStorage.setItem('envfix_org_id', oId);
                localStorage.setItem('envfix_org_api_key', key);
            }
            
            document.getElementById('auth-modal').classList.remove('active');
            fetchDashboardData();
        }

        // Check auth on load
        window.addEventListener('DOMContentLoaded', () => {
            const mode = localStorage.getItem('envfix_mode') || 'team';
            setMode(mode);
            if(mode === 'team') {
                const tId = localStorage.getItem('envfix_team_id');
                const key = localStorage.getItem('envfix_api_key');
                if(tId && key) {
                    document.getElementById('teamIdInput').value = tId;
                    document.getElementById('apiKeyInput').value = key;
                    fetchDashboardData();
                } else {
                    openAuthModal();
                }
            } else {
                const oId = localStorage.getItem('envfix_org_id');
                const key = localStorage.getItem('envfix_org_api_key');
                if(oId && key) {
                    document.getElementById('orgIdInput').value = oId;
                    document.getElementById('orgApiKeyInput').value = key;
                    fetchDashboardData();
                } else {
                    openAuthModal();
                }
            }
        });
        
        async function fetchDashboardData() {
            const mode = localStorage.getItem('envfix_mode') || 'team';
            
            document.getElementById('dashboard-content').classList.remove('active');
            document.getElementById('org-dashboard-content').style.display = 'none';
            document.getElementById('empty-state').classList.remove('active');
            document.getElementById('error-state').classList.remove('active');
            document.getElementById('loading-state').classList.add('active');
            document.getElementById('trial-badge').style.display = 'none';
            
            if (mode === 'team') {
                await fetchTeamData();
            } else {
                await fetchOrgData();
            }
        }
        
        async function fetchOrgData() {
            const oId = localStorage.getItem('envfix_org_id');
            const key = localStorage.getItem('envfix_org_api_key');
            
            try {
                const response = await fetch(`${API_BASE}/organizations/${oId}/overview`, {
                    headers: { 'X-API-Key': key }
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                document.getElementById('loading-state').classList.remove('active');
                
                if (!data.team_breakdown || data.team_breakdown.length === 0) {
                    document.getElementById('empty-state').classList.add('active');
                    return;
                }
                
                document.getElementById('org-dashboard-content').style.display = 'block';
                
                document.getElementById('org-val-dollars').textContent = `$${Math.round(data.estimated_dollars_saved).toLocaleString()}`;
                document.getElementById('org-val-hours').textContent = Math.round(data.estimated_hours_saved).toLocaleString();
                document.getElementById('org-val-machines').textContent = data.total_machines;
                document.getElementById('org-val-secrets').textContent = data.redacted_secrets_count;
                
                // Render health
                let healthHtml = '';
                for (const [cname, stats] of Object.entries(data.doctor_scan_health)) {
                    healthHtml += `<div style="margin-bottom: 0.5rem; display: flex; justify-content: space-between;">
                        <span>${cname}</span>
                        <span>
                            <span style="color: var(--success);">${Math.round(stats.clean_pct)}% Clean</span> /
                            <span style="color: var(--danger);">${Math.round(stats.flagged_pct)}% Flagged</span>
                        </span>
                    </div>`;
                }
                document.getElementById('org-doctor-health').innerHTML = healthHtml || "No recent scans.";
                
                // Render breakdown
                let breakdownHtml = '';
                for (const t of data.team_breakdown) {
                    const sr = t.success_rate !== null ? `${Math.round(t.success_rate)}%` : 'N/A';
                    breakdownHtml += `
                        <tr style="border-bottom: 1px solid var(--card-border);">
                            <td style="padding: 10px;">${t.id}</td>
                            <td style="padding: 10px;">${t.name}</td>
                            <td style="padding: 10px;">${t.total_events}</td>
                            <td style="padding: 10px;">${sr}</td>
                            <td style="padding: 10px; color: var(--success);">$${Math.round(t.estimated_dollars_saved).toLocaleString()}</td>
                        </tr>
                    `;
                }
                document.getElementById('org-team-breakdown').innerHTML = breakdownHtml;

            } catch(e) {
                document.getElementById('loading-state').classList.remove('active');
                document.getElementById('error-state').classList.add('active');
                document.getElementById('error-msg').textContent = e.message;
            }
        }
        
        async function fetchTeamData() {
            const tId = localStorage.getItem('envfix_team_id');
            const key = localStorage.getItem('envfix_api_key');
            
            try {
                const response = await fetch(`${API_BASE}/teams/${tId}/stats`, {
                    headers: { 'X-API-Key': key }
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                renderDashboard(data);
                
                // Show trial badge if applicable
                if (data.plan === "trial") {
                    document.getElementById('trial-badge').style.display = 'block';
                    document.getElementById('val-trial-used').textContent = data.total_events;
                    document.getElementById('val-trial-limit').textContent = data.trial_events_limit;
                }
                
            } catch (e) {
                document.getElementById('loading-state').classList.remove('active');
                document.getElementById('error-state').classList.add('active');
                document.getElementById('error-msg').textContent = e.message;
            }
        }
"""

html = html.replace(old_js_start, new_js_start)

# In the original fetchDashboardData logic, we need to remove the duplicate function since we replaced it.
# The original code has:
#        async function fetchDashboardData() { ... }
# We need to replace the original fetchDashboardData() with nothing, as we embedded it in new_js_start.

original_fetchDashboardData = """        async function fetchDashboardData() {
            const tId = localStorage.getItem('envfix_team_id');
            const key = localStorage.getItem('envfix_api_key');
            
            document.getElementById('dashboard-content').classList.remove('active');
            document.getElementById('empty-state').classList.remove('active');
            document.getElementById('error-state').classList.remove('active');
            document.getElementById('loading-state').classList.add('active');
            document.getElementById('trial-badge').style.display = 'none';

            try {
                const response = await fetch(`${API_BASE}/teams/${tId}/stats`, {
                    headers: {
                        'X-API-Key': key
                    }
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                renderDashboard(data);
                
                // Show trial badge if applicable
                if (data.plan === "trial") {
                    document.getElementById('trial-badge').style.display = 'block';
                    document.getElementById('val-trial-used').textContent = data.total_events;
                    document.getElementById('val-trial-limit').textContent = data.trial_events_limit;
                }
                
            } catch (e) {
                document.getElementById('loading-state').classList.remove('active');
                document.getElementById('error-state').classList.add('active');
                document.getElementById('error-msg').textContent = e.message;
            }
        }"""

html = html.replace(original_fetchDashboardData, "")

with open("envfix-dashboard/index.html", "w", encoding="utf-8") as f:
    f.write(html)
