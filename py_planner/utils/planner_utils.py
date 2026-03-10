from datetime import datetime, timedelta
import json
import os

class PlannerLogic:
    def __init__(self, settings=None):
        self.default_settings = {
            "shiftHours": 8,
            "workingDays": [1, 2, 3, 4, 5], # Mon-Fri
            "publicHolidays": [],
            "workingSaturdays": []
        }
        self.settings = settings or self.default_settings

    def safe_float(self, val):
        try:
            if val is None: return 0.0
            if isinstance(val, (int, float)): return float(val)
            # Remove currency, commas, percentages and whitespace
            s = str(val).replace(",", "").replace("%", "").replace("MUR", "").replace("Rs", "").strip()
            if not s or s.lower() == "none": return 0.0
            return float(s)
        except:
            return 0.0

    def safe_date(self, val):
        if isinstance(val, datetime):
            return val.replace(tzinfo=None)
        if not val or val == "None" or val == "":
            return datetime.min
            
        s = str(val).strip()
        # 1. Try ISO (Normalize Z and space/T)
        cleaned_s = s.replace("Z", "").replace(" ", "T")
        try:
            dt = datetime.fromisoformat(cleaned_s)
            return dt.replace(tzinfo=None) # Always naive
        except: pass
            
        # 2. Try common formats
        formats = [
            "%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d", "%d/%m/%Y", 
            "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d",
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
            "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                return dt.replace(tzinfo=None)
            except: continue
                
        # 3. Try short format DD-MMM (Assume current year)
        try:
            dt = datetime.strptime(s, "%d-%b")
            return dt.replace(year=datetime.now().year, tzinfo=None)
        except: pass
            
        return datetime.min

    def normalize_status(self, status):
        """Standardizes status strings for consistent dashboard reporting."""
        if not status: return "pending"
        s = str(status).lower().strip().replace(" ", "_").replace("-", "_")
        if s in ["completed", "done", "finished"]: return "completed"
        if s in ["in_progress", "running", "started", "active"]: return "in_progress"
        if s in ["hold", "on_hold", "paused", "blocked"]: return "on_hold"
        if s in ["not_started", "pending", "queued", "waiting"]: return "pending"
        if s in ["cancelled", "deleted", "rejected"]: return "cancelled"
        return "pending"

    def normalize_category(self, cat):
        """Standardizes category strings for consistent dashboard filtering."""
        if not cat: return "production"
        c = str(cat).lower().strip().replace(" ", "_")
        if "planner" in c or "production" in c: return "production"
        if "finishing" in c: return "finishing"
        if "packing" in c: return "packing"
        if "delivery" in c: return "delivery"
        return "production"

    def is_working_day(self, date):
        date_str = date.strftime("%Y-%m-%d")
        if date_str in self.settings.get("workingSaturdays", []):
            return True
        if date.weekday() + 1 not in self.settings.get("workingDays", [1, 2, 3, 4, 5]):
            return False
        if date_str in self.settings.get("publicHolidays", []):
            return False
        return True

    def apply_sequential_schedule(self, jobs, machine_name=None):
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 1. Calculate capacity used by completed jobs
        capacity_used = {} # date_key -> hours
        for job in jobs:
            if job.get("status") == "completed" and job.get("schedule"):
                for date_str, hrs in job["schedule"].items():
                    capacity_used[date_str] = capacity_used.get(date_str, 0) + self.safe_float(hrs)

        # 2. Pack pending jobs
        day_offset = 0
        hours_used_on_day = 0
        
        # Determine specific limit for this machine or fallback to general setting
        machine_shifts = self.settings.get("machineShifts", {})
        max_shift = self.safe_float(machine_shifts.get(machine_name, self.settings.get("shiftHours", 8)))

        updated_jobs = []
        for job in jobs:
            if job.get("status") == "completed":
                updated_jobs.append(job)
                continue
            
            if not job.get("visible", True):
                job["schedule"] = {}
                updated_jobs.append(job)
                continue

            mc_time = self.safe_float(job.get("mcTime", 0))
            if mc_time <= 0:
                job["schedule"] = {}
                updated_jobs.append(job)
                continue

            schedule = {}
            remaining = mc_time

            while remaining > 0:
                current_date = today + timedelta(days=day_offset)
                if not self.is_working_day(current_date):
                    day_offset += 1
                    hours_used_on_day = 0
                    continue

                date_key = current_date.strftime("%d-%b")
                locked_on_day = capacity_used.get(date_key, 0)
                available = max(0.0, max_shift - locked_on_day - hours_used_on_day)

                if available <= 0:
                    day_offset += 1
                    hours_used_on_day = 0
                    continue

                fill = min(remaining, available)
                current_hrs = self.safe_float(schedule.get(date_key, 0))
                schedule[date_key] = f"{round(current_hrs + fill, 2):g}"
                
                remaining -= fill
                hours_used_on_day += fill

                if hours_used_on_day + locked_on_day >= max_shift:
                    day_offset += 1
                    hours_used_on_day = 0

            job["schedule"] = schedule
            updated_jobs.append(job)
        return updated_jobs

    def calculate_efficiency_kpis(self, machines, start_date=None, end_date=None, machine_filter="all", category_filter="all"):
        metrics = []
        for name, machine in machines.items():
            if machine_filter != "all" and name != machine_filter:
                continue
            
            m_cat = self.normalize_category(machine.get("category", "production"))
            if category_filter != "all" and m_cat != category_filter:
                continue
                
            jobs = machine.get("jobs", [])
            completed = []
            for j in jobs:
                status = self.normalize_status(j.get("status"))
                if status == "completed":
                    c_dt = self.safe_date(j.get("completedAt"))
                    if c_dt == datetime.min:
                        c_dt = self.safe_date(j.get("deliveryDate"))
                        
                    # Filter
                    if c_dt != datetime.min:
                        if start_date and end_date:
                            if not (start_date <= c_dt <= end_date):
                                continue
                    else:
                        # LENIENT STRICTNESS: Only exclude undated jobs if range is active AND narrowband (< 350 days)
                        if start_date and end_date:
                            range_days = (end_date - start_date).days
                            if range_days < 350:
                                continue
                    completed.append(j)

            tot_mc = sum(self.safe_float(j.get("mcTime", 0)) for j in completed)
            tot_meters = sum(self.safe_float(j.get("meters", 0)) for j in completed)
            tot_rev = sum(self.safe_float(j.get("totalAmt", 0)) for j in completed)
            
            # Avg Cycle Time calculation
            tot_cycle_hrs = 0
            for j in completed:
                try:
                    s = self.safe_date(j.get("startedAt"))
                    e = self.safe_date(j.get("completedAt"))
                    if s != datetime.min and e != datetime.min:
                        tot_cycle_hrs += (e - s).total_seconds() / 3600
                except: pass

            metrics.append({
                "name": name,
                "avgMcTime": tot_mc / len(completed) if completed else 0,
                "mcTime1000m": (tot_mc / tot_meters) * 1000 if tot_meters > 0 else 0,
                "revPerHour": tot_rev / tot_mc if tot_mc > 0 else 0,
                "avgCycle": tot_cycle_hrs / len(completed) if completed else 0,
                "totalJobs": len(jobs),
                "completedCount": len(completed)
            })
        return metrics

    def calculate_financial_kpis(self, machines, start_date=None, end_date=None, machine_filter="all", category_filter="all"):
        all_comp = []
        for m_name, machine in machines.items():
            if machine_filter != "all" and m_name != machine_filter:
                continue
                
            m_cat = self.normalize_category(machine.get("category", "production"))
            if category_filter != "all" and m_cat != category_filter:
                continue
            
            jobs = machine.get("jobs", [])
            for j in jobs:
                status = self.normalize_status(j.get("status"))
                if status == "completed":
                    c_dt = self.safe_date(j.get("completedAt"))
                    if c_dt == datetime.min:
                        c_dt = self.safe_date(j.get("deliveryDate"))
                        
                    # Filter
                    if c_dt != datetime.min:
                        if start_date and end_date:
                            if not (start_date <= c_dt <= end_date):
                                continue
                    else:
                        # LENIENT STRICTNESS
                        if start_date and end_date:
                            range_days = (end_date - start_date).days
                            if range_days < 350:
                                continue
                    all_comp.append(j)

        monthly = {}
        customer = {}
        jtype = {}

        matrix_data = []
        for job in all_comp:
            try:
                dt = datetime.fromisoformat(job["completedAt"].replace("Z", ""))
                m_key = dt.strftime("%b %y")
                monthly[m_key] = monthly.get(m_key, 0) + self.safe_float(job.get("totalAmt", 0))
            except: pass
            
            c = job.get("customer", "Unknown")
            customer[c] = customer.get(c, 0) + self.safe_float(job.get("totalAmt", 0))
            
            t = job.get("description", "General")
            jtype[t] = jtype.get(t, 0) + self.safe_float(job.get("totalAmt", 0))

            mc_time = self.safe_float(job.get("mcTime", 0))
            total_amt = self.safe_float(job.get("totalAmt", 0))
            if mc_time > 0:
                matrix_data.append({
                    "pjc": job.get("pjc", "N/A"),
                    "mcTime": mc_time,
                    "revPerHour": total_amt / mc_time,
                    "totalAmt": total_amt,
                    "customer": c
                })

        total_rev = sum(self.safe_float(j.get("totalAmt", 0)) for j in all_comp)
        return {
            "monthly": monthly,
            "customer": sorted(customer.items(), key=lambda x: x[1], reverse=True)[:10],
            "type": sorted(jtype.items(), key=lambda x: x[1], reverse=True)[:8],
            "totalRevenue": total_rev,
            "avgRevenue": total_rev / len(all_comp) if all_comp else 0,
            "jobCount": len(all_comp),
            "matrixData": matrix_data
        }

    def calculate_strategic_kpis(self, machines, start_date=None, end_date=None, machine_filter="all", category_filter="all"):
        all_jobs = []
        for m_name, machine in machines.items():
            if machine_filter != "all" and m_name != machine_filter:
                continue
                
            m_cat = self.normalize_category(machine.get("category", "production"))
            if category_filter != "all" and m_cat != category_filter:
                continue
                
            all_jobs.extend(machine.get("jobs", []))
            
        completed = []
        filtered_all = []
        for j in all_jobs:
            status = self.normalize_status(j.get("status"))
            
            # Determine primary date for filtering
            # Fallback Sequence: CompletedAt -> DeliveryDate -> OrderDate (pjcIn)
            if status == "completed":
                j_dt = self.safe_date(j.get("completedAt"))
                if j_dt == datetime.min:
                    j_dt = self.safe_date(j.get("deliveryDate"))
            else:
                j_dt = self.safe_date(j.get("deliveryDate"))
                if j_dt == datetime.min:
                    j_dt = self.safe_date(j.get("pjcIn"))
            
            # Apply Filter: If date exists (not min), respect range. 
            if j_dt != datetime.min:
                if start_date and end_date:
                    if not (start_date <= j_dt <= end_date):
                        continue
            else:
                # LENIENT STRICTNESS: Only exclude undated jobs if range is active AND narrowband (< 350 days)
                if start_date and end_date:
                    range_days = (end_date - start_date).days
                    if range_days < 350:
                        continue
                    
            filtered_all.append(j)
            if status == "completed":
                completed.append(j)
                
        all_jobs = filtered_all # Only rank complexity for filtered jobs

        # 1. Complexity Ranking
        complexity = []
        jtype = {}
        for job in all_jobs:
            raw_cv = str(job.get("colorsVarnish", "1")).split('+')[0]
            colors = int(raw_cv) if raw_cv.isdigit() else 1
            meters = self.safe_float(job.get("meters", 0))
            time = self.safe_float(job.get("mcTime", 0)) or 1
            ratio = (time / meters) * 1000 if meters > 0 else 0
            score = (colors + 1) * (ratio + 1)
            complexity.append({
                "pjc": job.get("pjc", "N/A"),
                "customer": job.get("customer", "N/A"),
                "score": round(score, 2),
                "desc": job.get("description", "")
            })
            t = job.get("description", "General")
            jtype[t] = jtype.get(t, 0) + 1

        # 2. Delayed Jobs
        delays = {}
        for job in completed:
            try:
                c_at = self.safe_date(job["completedAt"])
                d_date = self.safe_date(job["deliveryDate"])
                if c_at > d_date:
                    cust = job.get("customer", "Unknown")
                    delays[cust] = delays.get(cust, 0) + 1
            except: pass

        # 3. Monthly Trends (Revenue vs Hours)
        monthly_stats = {}
        for job in completed:
            try:
                dt = self.safe_date(job["completedAt"])
                m_key = dt.strftime("%b %y")
                if m_key not in monthly_stats: monthly_stats[m_key] = {"revenue": 0, "hours": 0}
                monthly_stats[m_key]["revenue"] += self.safe_float(job.get("totalAmt", 0))
                monthly_stats[m_key]["hours"] += self.safe_float(job.get("mcTime", 0))
            except: pass

        # 4. Top Customers (Revenue & Time)
        cust_rev = {}
        cust_time = {}
        for job in all_jobs:
            c = job.get("customer", "Unknown")
            cust_rev[c] = cust_rev.get(c, 0) + self.safe_float(job.get("totalAmt", 0))
            cust_time[c] = cust_time.get(c, 0) + self.safe_float(job.get("mcTime", 0))

        # 5. Profitability Risk (Lowest Rev/Hr)
        profitability = []
        for c in cust_rev:
            rev = cust_rev[c]
            time = cust_time[c]
            if time > 5: # Only significant customers
                profitability.append({
                    "name": c,
                    "revPerHour": rev / time,
                    "totalTime": time
                })

        return {
            "complexity": sorted(complexity, key=lambda x: x["score"], reverse=True)[:8],
            "delays": sorted(delays.items(), key=lambda x: x[1], reverse=True)[:10],
            "totalDelays": sum(delays.values()),
            "type": sorted(jtype.items(), key=lambda x: x[1], reverse=True)[:8],
            "monthly_trends": monthly_stats,
            "top_revenue": sorted(cust_rev.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_time": sorted(cust_time.items(), key=lambda x: x[1], reverse=True)[:10],
            "profitability": sorted(profitability, key=lambda x: x["revPerHour"])[:10]
        }

    def get_summary_stats(self, machines, start_date=None, end_date=None, status_filter=None):
        """
        Aggregates MUR total and job counts by status across all categories.
        Filters by deliveryDate for active jobs and completedAt for completed jobs.
        If status_filter is provided (list or string), revenue 
        and customer stats are filtered to ONLY include those jobs.
        """
        categories = ["production", "finishing", "packing", "delivery"]
        stats = {cat: {
            "rev": 0.0,
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "on_hold": 0,
            "cancelled": 0,
            "total_jobs": 0,
            "meters": 0.0,
            "mcTime": 0.0
        } for cat in categories}
        
        customer_revenue = {} # To track top customers for the period

        # Normalize filter (handle list or string)
        target_statuses = []
        if status_filter:
            if isinstance(status_filter, str):
                if status_filter.lower() != "all":
                    target_statuses = [self.normalize_status(status_filter)]
            elif isinstance(status_filter, list):
                target_statuses = [self.normalize_status(s) for s in status_filter if s.lower() != "all"]

        for name, machine in machines.items():
            cat = self.normalize_category(machine.get("category", "production"))
            if cat not in stats: continue
            
            jobs = machine.get("jobs", [])
            for j in jobs:
                status = self.normalize_status(j.get("status"))
                
                # Determine relevant date for filtering
                # Fallback Sequence: CompletedAt -> DeliveryDate -> OrderDate (pjcIn)
                if status == "completed":
                    job_date = self.safe_date(j.get("completedAt"))
                    if job_date == datetime.min:
                        job_date = self.safe_date(j.get("deliveryDate"))
                else:
                    job_date = self.safe_date(j.get("deliveryDate"))
                    if job_date == datetime.min:
                        job_date = self.safe_date(j.get("pjcIn"))

                # Apply Date Filter: If date exists (not min), respect range.
                if job_date != datetime.min:
                    if start_date and end_date:
                        if not (start_date <= job_date <= end_date):
                            continue
                else:
                    # LENIENT STRICTNESS: Only exclude undated jobs if range is active AND narrowband (< 350 days)
                    if start_date and end_date:
                        range_days = (end_date - start_date).days
                        if range_days < 350:
                            continue
                
                # REVENUE & COUNT FILTERING: Only update stats if it matches the status filter
                if target_statuses and status not in target_statuses:
                    continue

                # Update Stats
                stats[cat][status] += 1
                stats[cat]["total_jobs"] += 1
                
                rev = self.safe_float(j.get("totalAmt", 0))
                stats[cat]["rev"] += rev
                stats[cat]["meters"] += self.safe_float(j.get("meters", 0))
                stats[cat]["mcTime"] += self.safe_float(j.get("mcTime", 0))
                
                # Customer tracking
                cust = j.get("customer", "Unknown")
                customer_revenue[cust] = customer_revenue.get(cust, 0) + rev

        return {
            "categories": stats,
            "top_customers": sorted(customer_revenue.items(), key=lambda x: x[1], reverse=True)[:5],
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

def load_planner_data(file_path):
    import time
    if not os.path.exists(file_path):
        return {"machines": {}, "appSettings": {"shiftHours": 8}}
    
    # Retry logic for Windows file locks/concurrent writes
    for attempt in range(3):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, PermissionError) as e:
            if attempt < 2:
                time.sleep(0.1)
                continue
            print(f"CRITICAL: Failed to load data from {file_path}: {e}")
            # Return minimum valid structure as absolute fallback to prevent crash
            return {"machines": {}, "appSettings": {"shiftHours": 8}}

def save_planner_data(file_path, data):
    import tempfile
    import time
    
    if not file_path:
        print("WARNING: No file path provided to save_planner_data.")
        return

    # Use the same directory for temp file to ensure os.replace works across the same volume
    dir_name = os.path.dirname(file_path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
        
    fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        # Robust replace for Windows
        for attempt in range(3):
            try:
                if os.path.exists(file_path):
                    os.chmod(file_path, 0o666) # Ensure writable
                os.replace(temp_path, file_path)
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.1)
                    continue
                raise
    except Exception as e:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass
        raise e
