#!/usr/bin/env python3
"""
Seed the database with job sources from major tech companies.
Comprehensive list including Big Tech, AI, Enterprise, Finance, and more.

Usage:
    cd /Users/chundu/jobportal/backend
    python tools/seed_companies.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import IngestionSource

# Comprehensive list of tech companies with their ATS info
# For Workday: ats_company_slug format is "company:wd#:site"
COMPANIES = [
    # ===========================================
    # BIG TECH - WORKDAY
    # ===========================================
    {"name": "Microsoft", "ats_type": "workday", "slug": "microsoft:wd5:External"},
    {"name": "Amazon", "ats_type": "workday", "slug": "amazon:wd5:AmazonJobs"},
    {"name": "AWS", "ats_type": "workday", "slug": "amazon:wd5:AWSJobs"},
    {"name": "Google", "ats_type": "workday", "slug": "google:wd1:External"},
    {"name": "Meta", "ats_type": "workday", "slug": "meta:wd5:External"},
    {"name": "Apple", "ats_type": "workday", "slug": "apple:wd1:External_Career"},
    {"name": "NVIDIA", "ats_type": "workday", "slug": "nvidia:wd5:NVIDIAExternalCareerSite"},

    # ===========================================
    # AI COMPANIES
    # ===========================================
    # Lever
    {"name": "OpenAI", "ats_type": "lever", "slug": "openai"},
    {"name": "Anthropic", "ats_type": "lever", "slug": "Anthropic"},
    {"name": "xAI", "ats_type": "lever", "slug": "xai"},
    {"name": "Scale AI", "ats_type": "lever", "slug": "scaleai"},
    {"name": "Mistral AI", "ats_type": "lever", "slug": "mistral"},
    {"name": "Hugging Face", "ats_type": "lever", "slug": "huggingface"},
    {"name": "Replicate", "ats_type": "lever", "slug": "replicate"},
    {"name": "Midjourney", "ats_type": "lever", "slug": "midjourney"},

    # Ashby
    {"name": "Character AI", "ats_type": "ashby", "slug": "character"},
    # Cohere uses dedicated Lever scraper (backend/scrapers/custom/cohere.py)
    {"name": "Together AI", "ats_type": "ashby", "slug": "togetherai"},
    {"name": "Baseten", "ats_type": "ashby", "slug": "baseten"},
    {"name": "Lambda", "ats_type": "ashby", "slug": "lambda"},
    {"name": "Crusoe Energy", "ats_type": "ashby", "slug": "crusoe"},
    {"name": "CoreWeave", "ats_type": "ashby", "slug": "coreweave"},
    {"name": "Perplexity", "ats_type": "ashby", "slug": "perplexity"},
    {"name": "Adept AI", "ats_type": "ashby", "slug": "adept"},
    {"name": "Anyscale", "ats_type": "ashby", "slug": "anyscale"},
    {"name": "Modal", "ats_type": "ashby", "slug": "modal"},
    {"name": "Weights & Biases", "ats_type": "ashby", "slug": "wandb"},
    {"name": "Writer", "ats_type": "ashby", "slug": "writer"},
    {"name": "Glean", "ats_type": "ashby", "slug": "glean"},
    {"name": "You.com", "ats_type": "ashby", "slug": "you"},

    # ===========================================
    # SOCIAL / CONSUMER
    # ===========================================
    {"name": "TikTok", "ats_type": "workday", "slug": "bytedance:wd5:TikTok"},
    {"name": "ByteDance", "ats_type": "workday", "slug": "bytedance:wd5:ByteDance"},
    {"name": "Snap", "ats_type": "workday", "slug": "snap:wd5:Snap"},
    {"name": "Adobe", "ats_type": "workday", "slug": "adobe:wd5:external"},
    {"name": "Netflix", "ats_type": "workday", "slug": "netflix:wd5:External"},
    {"name": "Spotify", "ats_type": "workday", "slug": "spotify:wd5:External"},
    {"name": "Pinterest", "ats_type": "workday", "slug": "pinterest:wd5:External"},
    {"name": "Reddit", "ats_type": "workday", "slug": "reddit:wd5:Reddit"},
    {"name": "Discord", "ats_type": "workday", "slug": "discord:wd5:Discord"},
    {"name": "Roblox", "ats_type": "workday", "slug": "roblox:wd5:Roblox"},
    {"name": "EA", "ats_type": "workday", "slug": "electronicarts:wd5:External"},
    {"name": "Etsy", "ats_type": "workday", "slug": "etsy:wd5:Etsy"},

    # ===========================================
    # ENTERPRISE / SaaS
    # ===========================================
    {"name": "Salesforce", "ats_type": "workday", "slug": "salesforce:wd12:External_Career_Site"},
    {"name": "Slack", "ats_type": "workday", "slug": "salesforce:wd12:Slack"},
    {"name": "Workday", "ats_type": "workday", "slug": "workday:wd5:External"},
    {"name": "ServiceNow", "ats_type": "workday", "slug": "servicenow:wd5:External"},
    {"name": "Zoom", "ats_type": "workday", "slug": "zoom:wd5:Zoom"},
    {"name": "Zendesk", "ats_type": "workday", "slug": "zendesk:wd5:Zendesk"},
    {"name": "Atlassian", "ats_type": "workday", "slug": "atlassian:wd5:External"},
    {"name": "DocuSign", "ats_type": "workday", "slug": "docusign:wd5:External"},
    {"name": "Box", "ats_type": "workday", "slug": "box:wd5:Box"},
    {"name": "Dropbox", "ats_type": "workday", "slug": "dropbox:wd5:Dropbox"},
    {"name": "Snowflake", "ats_type": "workday", "slug": "snowflake:wd5:External"},
    {"name": "Databricks", "ats_type": "workday", "slug": "databricks:wd5:External"},
    {"name": "Palantir", "ats_type": "workday", "slug": "palantir:wd5:External"},
    {"name": "Splunk", "ats_type": "workday", "slug": "splunk:wd5:External"},
    {"name": "Veeva", "ats_type": "workday", "slug": "veeva:wd5:External"},
    {"name": "Dynatrace", "ats_type": "workday", "slug": "dynatrace:wd5:External"},
    {"name": "Intuit", "ats_type": "workday", "slug": "intuit:wd5:External"},
    {"name": "SAP", "ats_type": "workday", "slug": "sap:wd5:External"},
    {"name": "Oracle", "ats_type": "workday", "slug": "oracle:wd5:External"},
    {"name": "IBM", "ats_type": "workday", "slug": "ibm:wd5:External"},

    # ===========================================
    # INFRASTRUCTURE / CLOUD
    # ===========================================
    {"name": "Cloudflare", "ats_type": "workday", "slug": "cloudflare:wd5:External"},
    {"name": "Datadog", "ats_type": "workday", "slug": "datadog:wd5:External"},
    {"name": "Elastic", "ats_type": "workday", "slug": "elastic:wd5:External"},
    {"name": "MongoDB", "ats_type": "workday", "slug": "mongodb:wd5:External"},
    {"name": "Confluent", "ats_type": "workday", "slug": "confluent:wd5:External"},
    {"name": "VMware", "ats_type": "workday", "slug": "vmware:wd5:External"},
    {"name": "NetApp", "ats_type": "workday", "slug": "netapp:wd5:External"},
    {"name": "Nutanix", "ats_type": "workday", "slug": "nutanix:wd5:External"},
    {"name": "Akamai", "ats_type": "workday", "slug": "akamai:wd5:External"},
    {"name": "HPE", "ats_type": "workday", "slug": "hpe:wd5:External"},
    {"name": "Dell", "ats_type": "workday", "slug": "dell:wd5:External"},

    # Greenhouse
    {"name": "HashiCorp", "ats_type": "greenhouse", "slug": "hashicorp"},
    {"name": "dbt Labs", "ats_type": "greenhouse", "slug": "daboratoriesdbtlabs"},
    {"name": "Vercel", "ats_type": "greenhouse", "slug": "vercel"},
    {"name": "Grafana Labs", "ats_type": "greenhouse", "slug": "grafanalabs"},

    # Ashby
    {"name": "Supabase", "ats_type": "ashby", "slug": "supabase"},
    {"name": "Neon", "ats_type": "ashby", "slug": "neondatabase"},
    {"name": "Upstash", "ats_type": "ashby", "slug": "upstash"},
    {"name": "Temporal", "ats_type": "ashby", "slug": "temporal"},
    {"name": "Kong", "ats_type": "ashby", "slug": "kong"},
    {"name": "Pulumi", "ats_type": "ashby", "slug": "pulumi"},
    {"name": "Render", "ats_type": "ashby", "slug": "render"},
    {"name": "Starburst", "ats_type": "ashby", "slug": "starburst"},

    # ===========================================
    # SECURITY
    # ===========================================
    {"name": "CrowdStrike", "ats_type": "greenhouse", "slug": "crowdstrike"},
    {"name": "Palo Alto Networks", "ats_type": "workday", "slug": "paloaltonetworks:wd5:External"},
    {"name": "Okta", "ats_type": "workday", "slug": "okta:wd5:Okta"},
    {"name": "Fortinet", "ats_type": "workday", "slug": "fortinet:wd5:External"},
    {"name": "SentinelOne", "ats_type": "workday", "slug": "sentinelone:wd5:External"},
    {"name": "Lacework", "ats_type": "ashby", "slug": "lacework"},
    {"name": "Vanta", "ats_type": "ashby", "slug": "vanta"},

    # ===========================================
    # FINTECH / FINANCE
    # ===========================================
    {"name": "Capital One", "ats_type": "workday", "slug": "capitalone:wd5:CapitalOne"},
    {"name": "JPMorgan", "ats_type": "workday", "slug": "jpmorganchase:wd5:JPMorgan"},
    {"name": "Visa", "ats_type": "workday", "slug": "visa:wd5:External"},
    {"name": "Stripe", "ats_type": "workday", "slug": "stripe:wd5:External"},
    {"name": "Block (Square)", "ats_type": "workday", "slug": "block:wd5:Block"},
    {"name": "Coinbase", "ats_type": "workday", "slug": "coinbase:wd5:External"},
    {"name": "Revolut", "ats_type": "workday", "slug": "revolut:wd5:External"},
    {"name": "Klarna", "ats_type": "workday", "slug": "klarna:wd5:External"},
    {"name": "Checkout.com", "ats_type": "workday", "slug": "checkoutdotcom:wd5:External"},
    {"name": "Ramp", "ats_type": "ashby", "slug": "ramp"},
    {"name": "Plaid", "ats_type": "lever", "slug": "plaid"},

    # ===========================================
    # PRODUCTIVITY / DESIGN
    # ===========================================
    {"name": "Figma", "ats_type": "workday", "slug": "figma:wd5:Figma"},
    {"name": "Notion", "ats_type": "ashby", "slug": "notion"},
    {"name": "Canva", "ats_type": "workday", "slug": "canva:wd5:Canva"},
    {"name": "Airtable", "ats_type": "workday", "slug": "airtable:wd5:Airtable"},
    {"name": "Asana", "ats_type": "workday", "slug": "asana:wd5:Asana"},
    {"name": "Loom", "ats_type": "ashby", "slug": "loom"},
    {"name": "Lattice", "ats_type": "ashby", "slug": "lattice"},
    {"name": "Zapier", "ats_type": "ashby", "slug": "zapier"},
    {"name": "Deel", "ats_type": "ashby", "slug": "deel"},

    # ===========================================
    # ROBOTICS / AUTONOMOUS
    # ===========================================
    {"name": "Shield AI", "ats_type": "lever", "slug": "shieldai"},
    {"name": "Zoox", "ats_type": "lever", "slug": "zoox"},
    {"name": "Cruise", "ats_type": "lever", "slug": "cruise"},
    {"name": "Aurora", "ats_type": "lever", "slug": "aurora"},
    {"name": "Niantic", "ats_type": "lever", "slug": "niantic"},
    {"name": "SpaceX", "ats_type": "lever", "slug": "spacex"},
    {"name": "Neuralink", "ats_type": "lever", "slug": "neuralink"},
    {"name": "Anduril", "ats_type": "lever", "slug": "anduril"},
    {"name": "Intuitive Surgical", "ats_type": "workday", "slug": "intusurg:wd5:External"},

    # ===========================================
    # E-COMMERCE / CONSUMER TECH
    # ===========================================
    {"name": "Shopify", "ats_type": "workday", "slug": "shopify:wd5:External"},
    {"name": "Uber", "ats_type": "workday", "slug": "uber:wd5:Uber"},
    {"name": "Lyft", "ats_type": "workday", "slug": "lyft:wd5:Lyft"},
    {"name": "Airbnb", "ats_type": "workday", "slug": "airbnb:wd5:airbnb"},
    {"name": "DoorDash", "ats_type": "workday", "slug": "doordash:wd5:DoorDash"},
    {"name": "Instacart", "ats_type": "workday", "slug": "instacart:wd5:Instacart"},
    {"name": "Chewy", "ats_type": "workday", "slug": "chewy:wd5:External"},
    {"name": "Wish", "ats_type": "workday", "slug": "wish:wd5:External"},
    {"name": "Whatnot", "ats_type": "ashby", "slug": "whatnot"},

    # ===========================================
    # REAL ESTATE / TRAVEL
    # ===========================================
    {"name": "Zillow", "ats_type": "workday", "slug": "zillow:wd5:Zillow"},
    {"name": "Redfin", "ats_type": "workday", "slug": "redfin:wd5:External"},
    {"name": "Expedia", "ats_type": "workday", "slug": "expedia:wd5:External"},

    # ===========================================
    # TELECOM / MEDIA
    # ===========================================
    {"name": "Verizon", "ats_type": "workday", "slug": "verizon:wd5:External"},
    {"name": "T-Mobile", "ats_type": "workday", "slug": "tmobile:wd5:External"},
    {"name": "Comcast", "ats_type": "workday", "slug": "comcast:wd5:External"},
    {"name": "NBCUniversal", "ats_type": "workday", "slug": "nbcuniversal:wd5:External"},
    {"name": "Warner Bros", "ats_type": "workday", "slug": "warnerbros:wd5:External"},
    {"name": "Paramount", "ats_type": "workday", "slug": "paramount:wd5:External"},
    {"name": "Disney", "ats_type": "workday", "slug": "disney:wd5:External"},

    # ===========================================
    # SEMICONDUCTOR / HARDWARE
    # ===========================================
    {"name": "Intel", "ats_type": "workday", "slug": "intel:wd1:External"},
    {"name": "AMD", "ats_type": "workday", "slug": "amd:wd1:AMD"},
    {"name": "Qualcomm", "ats_type": "workday", "slug": "qualcomm:wd5:External"},
    {"name": "Broadcom", "ats_type": "workday", "slug": "broadcom:wd5:External"},
    {"name": "Marvell", "ats_type": "workday", "slug": "marvell:wd5:External"},
    {"name": "SambaNova", "ats_type": "greenhouse", "slug": "sambanova"},

    # ===========================================
    # DEVTOOLS / DEVELOPER
    # ===========================================
    {"name": "GitLab", "ats_type": "greenhouse", "slug": "gitlab"},
    {"name": "GitHub", "ats_type": "workday", "slug": "microsoft:wd5:GitHub"},
    {"name": "JetBrains", "ats_type": "greenhouse", "slug": "jetbrains"},
    {"name": "Postman", "ats_type": "greenhouse", "slug": "postman"},
    {"name": "CircleCI", "ats_type": "greenhouse", "slug": "circleci"},
    {"name": "Sourcegraph", "ats_type": "greenhouse", "slug": "sourcegraph91"},
    {"name": "Snyk", "ats_type": "greenhouse", "slug": "snyk"},
    {"name": "LaunchDarkly", "ats_type": "greenhouse", "slug": "launchdarkly"},
    {"name": "Replit", "ats_type": "lever", "slug": "replit"},
    {"name": "Linear", "ats_type": "ashby", "slug": "linear"},
    {"name": "Retool", "ats_type": "lever", "slug": "retool"},
    {"name": "Fly.io", "ats_type": "greenhouse", "slug": "flyio"},
    {"name": "Railway", "ats_type": "greenhouse", "slug": "railway"},
    {"name": "Webflow", "ats_type": "greenhouse", "slug": "webflow"},
    {"name": "PlanetScale", "ats_type": "greenhouse", "slug": "planetscale"},
    {"name": "Tailscale", "ats_type": "greenhouse", "slug": "tailscale"},
    {"name": "PostHog", "ats_type": "greenhouse", "slug": "posthog"},
    {"name": "Fivetran", "ats_type": "greenhouse", "slug": "fivetran"},
    {"name": "Stytch", "ats_type": "greenhouse", "slug": "stytch"},
    {"name": "Hasura", "ats_type": "greenhouse", "slug": "hasura"},

    # ===========================================
    # HEALTHCARE / BIOTECH
    # ===========================================
    {"name": "Abridge", "ats_type": "ashby", "slug": "abridge"},
    {"name": "Ro", "ats_type": "ashby", "slug": "ro"},
    {"name": "Tempus", "ats_type": "workday", "slug": "tempus:wd5:External"},
    {"name": "Agilent", "ats_type": "workday", "slug": "agilent:wd5:External"},

    # ===========================================
    # AIRLINES
    # ===========================================
    {"name": "United Airlines", "ats_type": "workday", "slug": "united:wd5:External"},
    {"name": "Delta", "ats_type": "workday", "slug": "delta:wd5:External"},
    {"name": "American Airlines", "ats_type": "workday", "slug": "americanairlines:wd5:External"},

    # ===========================================
    # OTHER ASHBY COMPANIES
    # ===========================================
    {"name": "1Password", "ats_type": "ashby", "slug": "1password"},
    {"name": "Decagon", "ats_type": "ashby", "slug": "decagon"},
    {"name": "Genmo", "ats_type": "ashby", "slug": "genmo"},
    {"name": "Roboflow", "ats_type": "ashby", "slug": "roboflow"},
    {"name": "Resend", "ats_type": "ashby", "slug": "resend"},
    {"name": "Relace", "ats_type": "ashby", "slug": "relace"},
    {"name": "Mintlify", "ats_type": "ashby", "slug": "mintlify"},
    {"name": "Cal.com", "ats_type": "ashby", "slug": "calcom"},
    {"name": "Axiom", "ats_type": "ashby", "slug": "axiom"},
    {"name": "Tinybird", "ats_type": "ashby", "slug": "tinybird"},
    {"name": "Rippling", "ats_type": "ashby", "slug": "rippling"},

    # ===========================================
    # NETWORKING / COMMS
    # ===========================================
    {"name": "Cisco", "ats_type": "workday", "slug": "cisco:wd5:External"},
    {"name": "Twilio", "ats_type": "workday", "slug": "twilio:wd5:External"},

    # ===========================================
    # ADDITIONAL COMPANIES
    # ===========================================
    {"name": "Brex", "ats_type": "ashby", "slug": "brex"},
    {"name": "Grammarly", "ats_type": "greenhouse", "slug": "grammarly"},
    {"name": "HubSpot", "ats_type": "workday", "slug": "hubspot:wd5:HubSpot"},
    {"name": "Robinhood", "ats_type": "workday", "slug": "robinhood:wd5:Robinhood"},
    {"name": "Unity", "ats_type": "workday", "slug": "unity:wd5:External"},
    {"name": "Waymo", "ats_type": "workday", "slug": "waymo:wd5:Waymo"},
    {"name": "X (Twitter)", "ats_type": "workday", "slug": "x:wd5:X"},
]


def get_career_url(ats_type: str, slug: str) -> str:
    """Generate career page URL from ATS type and slug."""
    if ats_type == "workday":
        parts = slug.split(":")
        if len(parts) == 3:
            company, region, site = parts
            return f"https://{company}.{region}.myworkdayjobs.com/{site}"
    elif ats_type == "greenhouse":
        return f"https://boards.greenhouse.io/{slug}"
    elif ats_type == "lever":
        return f"https://jobs.lever.co/{slug}"
    elif ats_type == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}"
    return ""


def seed_companies():
    """Seed the database with job sources"""
    db = SessionLocal()
    added = 0
    skipped = 0
    updated = 0

    try:
        for company in COMPANIES:
            ats_type = company["ats_type"]
            slug = company["slug"]
            name = company["name"]

            # Check if source already exists
            existing = db.query(IngestionSource).filter(
                IngestionSource.ats_type == ats_type,
                IngestionSource.ats_company_slug == slug
            ).first()

            if existing:
                # Update name if different
                if existing.company_name != name:
                    existing.company_name = name
                    updated += 1
                    print(f"  Updated: {name}")
                else:
                    skipped += 1
                continue

            # Create new source
            career_url = get_career_url(ats_type, slug)
            source = IngestionSource(
                ats_type=ats_type,
                ats_company_slug=slug,
                company_name=name,
                career_page_url=career_url,
                is_active=True,
                job_count=0
            )

            db.add(source)
            added += 1
            print(f"  Added: {name} ({ats_type})")

        db.commit()
        print(f"\n{'='*50}")
        print(f"Done! Added {added}, updated {updated}, skipped {skipped}")
        print(f"Total sources: {db.query(IngestionSource).count()}")

        # Print summary by ATS type
        print(f"\nBreakdown by ATS type:")
        for ats in ['workday', 'greenhouse', 'lever', 'ashby']:
            count = db.query(IngestionSource).filter(IngestionSource.ats_type == ats).count()
            print(f"  {ats}: {count}")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding job sources...\n")
    seed_companies()
