"""
IT / tech role detection from a job title (department, board category and
skills only break ties). Pure regex, no I/O - cheap enough for every scraped row.
Shared by the full-time pipeline and the contracts package (neither imports
the other for this).

    is_it_role(title, category=None, department=None, skills=None, ambiguous_default=False) -> bool
    it_category(title, category=None, department=None, skills=None, ambiguous_default=False) -> str | None
    classify_it(title, category=None, department=None, skills=None) -> ItDecision

Categories (IT_CATEGORIES): software, devops_sre_cloud, data, ml_ai, security,
network_systems_dba, qa, it_support, embedded_hw, product_program, design_ux,
tech_writing.

How a title is decided
----------------------
1. The title's primary segment (text before the first " - ", ",", "(", "|")
   is searched for role phrases; the phrase that ends last wins (the head noun
   of an English job title is at the end: "Software Sales Executive" is sales,
   "Salesforce Developer" is IT), ties go to the longer phrase. When the
   primary segment has no role phrase the whole title is searched.
2. An explicit IT phrase ("Data Engineer", "Help Desk Technician") -> IT;
   an explicit non-IT phrase ("Recruiter", "Process Engineer") -> not IT.
3. Ambiguous role words ("Engineer", "Analyst", "Architect", "Technician",
   "Consultant", "Project Manager", ...) are decided by qualifiers anywhere
   in the title (IT: software, data, cloud, SAP, IT, ... / non-IT:
   construction, clinical, manufacturing, radar, ...), then by the
   category / department text, then by skills (>= 2 known tech skills),
   then by the rule's lean (e.g. "Systems Engineer" leans IT,
   "Technician" leans non-IT). Undecided titles return
   ``ambiguous_default``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Optional

IT_CATEGORIES = (
    "software", "devops_sre_cloud", "data", "ml_ai", "security", "network_systems_dba",
    "qa", "it_support", "embedded_hw", "product_program", "design_ux", "tech_writing",
)

IN, OUT, AMB = "in", "out", "amb"


@dataclass(frozen=True)
class ItDecision:
    is_it: Optional[bool]  # None = undecided (ambiguous title, no context)
    category: Optional[str]  # an IT_CATEGORIES code when is_it (or the best guess when undecided)
    reason: str  # title | title_out | qualifier | qualifier_out | context | context_out | skills | lean | lean_out | ambiguous | no_match


# ------------------------------------------------------------------ normalize

_SUBS = (
    (re.compile(r"c\+\+", re.I), " cplusplus "),
    (re.compile(r"c#", re.I), " csharp "),
    (re.compile(r"(?<![a-z0-9])\.net\b", re.I), " dotnet "),
    (re.compile(r"\b(node|vue|next|react|angular|express)\.js\b", re.I), r" \1js "),
    (re.compile(r"&"), " and "),
    (re.compile(r"\bsr\.", re.I), "sr "),
    (re.compile(r"\bjr\.", re.I), "jr "),
)
_NON_WORD = re.compile(r"[^a-z0-9]+")
_SEGMENT_SPLIT = re.compile(r"\s[-–—|:/]\s|[,(\[|–—]|\s-(?=\S)|(?<=\S)-\s|(?<=[A-Za-z]{3})/(?=[A-Za-z]{3})")


def _norm(text: str) -> str:
    s = str(text or "")
    for rx, rep in _SUBS:
        s = rx.sub(rep, s)
    return " " + _NON_WORD.sub(" ", s.lower()).strip() + " "


# ------------------------------------------------------------------ rules
# (verdict, category, lean, pattern). Patterns run on normalized text (lowercase,
# single spaces, padded); they are wrapped in word boundaries.

_ERP = (r"salesforce|sfdc|servicenow|service now|workday|magento|adobe commerce|shopify|bigcommerce|commercetools|salesforce commerce|sap|abap|oracle|peoplesoft|netsuite|(?<!vehicle )dynamics|d365|guidewire|"
        r"dynamics 365|dynamics crm|microsoft dynamics|ms dynamics|pega|appian|mulesoft|veeva|epic|cerner|siebel|jde|jd edwards|infor|ifs|kronos|ukg|"
        r"coupa|ariba|anaplan|hubspot|marketo|sitecore|aem|adobe experience manager|sharepoint|"
        r"power platform|power apps?|power automate|outsystems|mendix|informatica|tableau|power bi|looker|"
        r"snowflake|databricks|splunk|jira|atlassian|confluence|m365|microsoft 365|office 365|o365|"
        r"intune|sccm|citrix|vmware|active directory|okta|sailpoint|cyberark|palo alto|fortinet|"
        r"cisco|juniper|ellucian|banner|blackbaud|yardi|murex|calypso|fis|fiserv|temenos|duck creek|"
        r"hris|hcm|erp|crm|ehr|emr")
_LANG = (r"java|javascript|typescript|python|golang|rust|ruby|rails|php|perl|scala|kotlin|swift|"
         r"objective c|cplusplus|csharp|dotnet|vb|cobol|mainframe|rpg|as400|plsql|pl sql|t sql|sql|"
         r"nodejs|node|reactjs|react|react native|angularjs|angular|vuejs|vue|nextjs|flutter|django|"
         r"spring|spring boot|laravel|unity|unreal|solidity|elixir|haskell|clojure|lisp|matlab|sas")
_ROLE_TAIL = (r"engineer|engineering|developer|development|dev|programmer|architect|administrator|admin|"
              r"consultant|analyst|specialist|lead|manager|sme|expert|tester|designer|modeler|modeller|"
              r"scientist|researcher|technician|tech|support|owner|coordinator|operator|officer|"
              r"strategist|director|head|principal|associate")
_TAIL = r"(?:(?:sr|senior|jr|junior|lead|staff|principal|i{1,3}|iv|v|[1-5]|level|l[1-5])\s+)*(?:" + _ROLE_TAIL + r")s?"

_RULES_SRC: list[tuple[str, Optional[str], Optional[bool], str]] = [
    # ---------------------------------------------------------------- IT: software
    (IN, "software", None, r"software|software (?:engineer|developer|development|engineering|architect|programmer)\w*"),
    (IN, "software", None, r"(?:sw|swe|sde|sdet|mts)"),
    (IN, "software", None, r"(?:r|go) (?:developer|programmer|engineer)s?"),
    (IN, "software", None, r"(?:frontend|front end|backend|back end|full stack|fullstack|devqa|github actions|gitlab)"),
    (IN, "software", None, r"member of (?:the )?technical staff"),
    (IN, "software", None, r"(?:developer|programmer|coder)s?"),
    (IN, "software", None, r"(?:web|backend|back end|frontend|front end|full stack|fullstack|mobile|ios|android|"
                           r"application|applications|app|api|integration|integrations|middleware|game|gameplay|"
                           r"graphics|rendering|compiler|kernel|systems software|ui|ux|ui ux|" + _LANG + r")\s+"
                           r"(?:(?:software|web|application|platform|systems?|stack|services?|and|or|" + _LANG + r")\s+)*"
                           r"(?:engineer|developer|programmer|architect|engineering|development|lead|dev)s?"),
    (IN, "software", None, r"(?:" + _LANG + r")\s+(?:\w+\s+){0,2}(?:engineer|developer|programmer|architect|lead|consultant)s?"),
    (IN, "software", None, r"(?:solutions?|enterprise|software|application|applications|technical|technology|integration|"
                           r"systems|salesforce|sap|servicenow|workday|it|platform|principal architect) architects?"),
    (IN, "software", None, r"(?:" + _ERP + r")(?:\s+\w+){0,3}\s+" + _TAIL),
    (IN, "software", None, r"techno functional|functional consultant|technical consultant|technical lead|tech lead|"
                           r"software manager|software development manager|application development manager|"
                           r"vp (?:of )?engineering|head of engineering|director of (?:software )?engineering|"
                           r"chief technology officer|cto|robotics software"),
    (IN, "software", None, r"application (?:owner|analyst|specialist|support analyst|consultant|developer)s?"),
    (IN, "software", None, r"(?:rpa|automation anywhere|uipath|blue prism) " + _TAIL),
    (IN, "software", None, r"hr (?:integrations?|systems|technology|information systems)(?:\s+\w+){0,2}\s+" + _TAIL),
    (IN, "software", None, r"(?:blockchain|smart contract|web3|crypto) (?:engineer|developer)s?"),
    # ---------------------------------------------------------------- IT: devops / sre / cloud
    (IN, "devops_sre_cloud", None, r"devops|dev ops|sre|site reliability|platform engineers?|platform engineering|"
                                   r"cloud(?: \w+)?(?: \w+)? " + _TAIL + r"|cloud|"
                                   r"(?:aws|azure|gcp|google cloud|kubernetes|k8s|terraform|openshift) (?:\w+ )?" + _TAIL + r"|"
                                   r"infrastructure (?:\w+ )?" + _TAIL + r"|build (?:and )?release engineers?|"
                                   r"release engineers?|ci cd engineers?|observability|finops"),
    # ---------------------------------------------------------------- IT: data
    (IN, "data", None, r"data (?:\w+ )?(?:engineer|engineering|architect|analyst|analytics|scientist|science|modeler|modeller|"
                       r"developer|warehouse|warehousing|platform|governance|steward|quality analyst|visualization|"
                       r"integration|migration|conversion|lead|manager)s?"),
    (IN, "data", None, r"analytics engineers?|business intelligence|biostatisticians?|statistical programmers?|bi (?:\w+ )?" + _TAIL + r"|etl|elt|big data|"
                       r"database (?:developer|engineer|architect|programmer)s?|"
                       r"(?:tableau|power bi|looker|snowflake|databricks|informatica|hadoop|spark|dbt) (?:\w+ )?" + _TAIL + r"|"
                       r"quantitative developer|statisticians?|decision scientist|analytics (?:manager|lead|specialist|consultant)"),
    # ---------------------------------------------------------------- IT: ML / AI
    (IN, "ml_ai", None, r"machine learning|ml (?:\w+ )?" + _TAIL + r"|mlops|ai ml|artificial intelligence|deep learning|"
                        r"computer vision|nlp|natural language processing|llm|genai|gen ai|generative ai|"
                        r"ai (?:\w+ ){0,2}(?:engineer|developer|architect|scientist|researcher|specialist|lead|"
                        r"consultant|engineering|platform|infrastructure|solutions?|product)s?|"
                        r"applied scientists?|prompt engineers?|research engineers?|(?:algo|algorithm) (?:\w+ )?(?:engineer|researcher|developer|scientist)s?"),
    (AMB, "ml_ai", None, r"researchers?|head of research"),
    # ---------------------------------------------------------------- IT: security
    (IN, "security", None, r"(?:cyber ?security|cyber|information security|infosec|it security|application security|"
                           r"appsec|product security|cloud security|network security|data security|security|"
                           r"devsecops|offensive security|identity and access management|iam|identity|grc)"
                           r"(?: \w+)? (?:engineer|architect|analyst|specialist|consultant|administrator|admin|"
                           r"manager|lead|operations|researcher|developer|director|auditor|tester|"
                           r"engineering|assessor)s?"),
    (IN, "security", None, r"cyber ?security|cyber|infosec|penetration testers?|pen testers?|pentesters?|ethical hackers?|"
                           r"red team\w*|blue team\w*|soc (?:analyst|engineer|lead|manager)s?|security operations center|"
                           r"threat (?:hunter|intelligence|detection|analyst)s?|incident response|vulnerability (?:\w+ )?" + _TAIL + r"|"
                           r"siem|firewall(?: \w+)?(?: " + _TAIL + r")?|it auditors?|it audit|it risk|information assurance|"
                           r"ciso|chief information security officer|information security officers?|isso|issm|information system security (?:officer|manager)|"
                           r"(?:sailpoint|cyberark|okta|ping|zscaler|crowdstrike|palo alto|fortinet|splunk) (?:\w+ )?" + _TAIL + r"|"
                           r"security clearance engineer|epic security (?:analyst|coordinator)s?"),
    # ---------------------------------------------------------------- IT: network / systems / DBA
    (IN, "network_systems_dba", None, r"network (?:\w+ )?(?:engineer|administrator|admin|architect|analyst|technician|"
                                      r"tech|specialist|operations|lead|manager|consultant|engineering)s?"),
    (IN, "network_systems_dba", True, r"systems? (?:\w+ )?(?:administrator|admin|administration)s?|sysadmins?|"
                                      r"(?:windows|linux|unix|vmware|citrix|storage|backup|exchange|active directory|"
                                      r"m365|microsoft 365|office 365|o365|intune|sccm|endpoint|wintel|virtualization|"
                                      r"messaging|collaboration|unified communications|voip|telecom|telecommunications|"
                                      r"wireless|lan|wan|noc|mainframe|middleware|server|servers|san|citrix|jamf|mac) "
                                      r"(?:\w+ )?(?:engineer|administrator|admin|architect|analyst|specialist|tech|"
                                      r"technician|systems programmer|operator|consultant|lead)s?"),
    (IN, "network_systems_dba", None, r"dbas?|database admin\w*|database administration|datacenter(?: \w+)?|sso(?: \w+)?|exchange online(?: \w+)?|"
                                      r"data center (?!facilities)(?:\w+ )?(?:technician|tech|engineer|operations|specialist|analyst)s?|"
                                      r"server (?:install )?(?:tech|technician)s?|noc|voip|packet core|"
                                      r"systems programmers?|it infrastructure|endpoint"),
    # ---------------------------------------------------------------- IT: QA
    (IN, "qa", None, r"qa(?: \w+)? (?:engineer|analyst|tester|lead|automation|manager|specialist|architect)s?|"
                     r"software (?:quality|test|testing|qa)(?: \w+)?(?: " + _TAIL + r")?|"
                     r"test automation|automation testers?|testers?|sdets?|software development engineer in test|"
                     r"(?:performance|load|manual|mobile|api|etl|uat|selenium|functional) (?:test|testing|qa)(?: " + _TAIL + r")?|"
                     r"uat (?:analyst|tester|lead)s?|test (?:analyst|lead|manager|architect)s?"),
    # ---------------------------------------------------------------- IT: support
    (IN, "it_support", None, r"help ?desk(?: \w+){0,3}|service ?desk(?: \w+){0,3}|technical support(?: \w+){0,3}|"
                             r"audio visual (?:support )?(?:technician|tech|specialist|engineer)s?|av (?:support )?(?:technician|tech|engineer)s?|"
                             r"desktop (?:support|technician|engineer|analyst|administrator)s?|deskside|end user (?:support|computing)|"
                             r"it (?:\w+ ){0,2}(?:support|technician|tech|specialist|analyst|administrator|admin|coordinator|manager|"
                             r"director|operations|engineer|lead|consultant|generalist|associate|intern|auditor|project manager|"
                             r"program manager|asset|procurement)s?|"
                             r"technical support(?: \w+)?(?: " + _TAIL + r")?|tech support|support engineers?|"
                             r"(?:pc|computer|imac|hardware refresh|deployment|field it|onsite it|it field) (?:\w+ )?(?:technician|tech|specialist|support)s?|"
                             r"production support(?: " + _TAIL + r")?|application support(?: " + _TAIL + r")?|l[123] support|tier [123] support|"
                             r"chief information officer|cio|vp (?:of )?it|head of it|information technology(?: \w+)?"),
    # ---------------------------------------------------------------- IT: embedded / hardware
    (IN, "embedded_hw", None, r"embedded|firmware|fpga|asic|vlsi|soc design|rtl|design verification|verification engineers?|"
                              r"(?:hardware|electronics|pcb|board|circuit|analog|digital|mixed signal|rf|silicon|"
                              r"power electronics|signal integrity) (?:\w+ )?(?:engineer|designer|design engineer|developer|architect)s?|"
                              r"hardware (?:design|engineering)|electronics engineers?"),
    # ---------------------------------------------------------------- IT: product / program / BA
    (IN, "product_program", None, r"(?:technical|it|software|digital|technology|data|cloud|platform|ai|erp|sap|salesforce|"
                                  r"infrastructure|agile|devops) (?:\w+ )?(?:product|program|project|delivery|portfolio|"
                                  r"implementation) (?:manager|lead|director|owner|coordinator|analyst)s?|"
                                  r"tpms?|product owners?|scrum masters?|agile coach\w*|release (?:manager|train engineer)s?|"
                                  r"(?:business )?systems? analysts?|technical business analysts?|it business analysts?|"
                                  r"technical program|technical product|technical project"),
    # ---------------------------------------------------------------- IT: design
    (IN, "design_ux", None, r"ux(?: \w+)?(?: \w+)? (?:designer|researcher|research|writer|architect|lead|manager|director|strategist|engineer)s?|"
                            r"ui(?: \w+)? designers?|user (?:experience|interface|research(?:er)?)|interaction designers?|"
                            r"product designers?|web designers?|design technologists?|visual designers?|ui ux|ux"),
    # ---------------------------------------------------------------- IT: technical writing
    (IN, "tech_writing", None, r"technical (?:writer|writing|editor|documentation|communicator)s?|documentation (?:engineer|specialist)s?|"
                               r"api (?:writer|documentation)|information developers?|docs engineers?"),

    # ---------------------------------------------------------------- ambiguous role words
    (AMB, "software", True, r"engineers?|engineering"),
    (AMB, "software", True, r"engineering (?:manager|lead|director)s?"),
    (AMB, "software", True, r"(?:senior|sr|staff|principal|lead|junior|jr) engineers?"),
    (AMB, "network_systems_dba", True, r"systems? (?:\w+ )?engineers?|systems? engineering|systems? operations engineers?"),
    (AMB, "software", True, r"(?:integration|applications?|solutions?|research|customer|forward deployed|"
                            r"implementation|automation|performance|entry level|associate|junior|graduate) engineers?"),
    (AMB, "software", False, r"(?:\w+ )?representatives?|reps?"),
    (AMB, "software", None, r"automation engineers?"),
    (AMB, "qa", True, r"quality assurance (?:\w+ )?(?:engineer|analyst|tester|lead)s?|test engineers?|test and evaluation|testing engineers?"),
    (AMB, "devops_sre_cloud", True, r"reliability engineers?"),
    (AMB, "embedded_hw", False, r"electrical engineers?|electrical (?:design )?engineering|validation engineers?|"
                                r"requirements engineers?|test technicians?"),
    (AMB, "software", True, r"architects?"),
    (AMB, "software", None, r"consultants?|consulting|sme|subject matter expert|specialist"),
    (AMB, "product_program", True, r"(?:project|program) managers?|pms?"),
    (AMB, "product_program", None, r"(?:project|program|delivery|portfolio|implementation|pmo) (?:manager|lead|director|analyst|coordinator|specialist)s?|"
                                   r"(?:project|program) management|pmo|managers?"),
    (AMB, "product_program", True, r"product (?:manager|management|lead|director)s?"),
    (AMB, "product_program", True, r"business (?:\w+ )?analysts?"),
    (AMB, "data", None, r"analysts?|reporting (?:analyst|specialist)s?"),
    (AMB, "it_support", False, r"technicians?|techs?"),
    (AMB, "ml_ai", False, r"(?:research |senior |sr |principal |staff )?scientists?"),
    (AMB, "design_ux", None, r"designers?"),
    (AMB, "software", True, r"technical (?:lead|manager|director|specialist|account manager)s?|technologists?"),
    (AMB, "product_program", False, r"coordinators?|change management|change managers?"),
    (AMB, "it_support", False, r"field engineers?|field service engineers?|operators?"),
    (AMB, "software", None, r"(?:product|solution|platform|design|feature|team) leads?|lead"),

    # ---------------------------------------------------------------- non-IT
    # retail / hospitality
    (OUT, None, None, r"cashiers?|store (?:\w+ )?(?:associate|manager|lead|clerk|director|supervisor|team member)s?|"
                      r"retail (?:\w+ )?(?:associate|sales|manager|lead|merchandiser|store|team member|specialist)s?|"
                      r"sales (?:floor|associate|assistant)s?|educators?|merchandis\w+|stockers?|stock (?:associate|clerk)s?|"
                      r"baristas?|bartenders?|(?:restaurant|food|banquet) servers?|servers? and bartenders?|cooks?|chefs?|"
                      r"dishwashers?|hosts?|hostess|housekeep\w*|room attendants?|guest (?:experience|services?) (?:\w+ )?(?:lead|associate|agent|manager|representative)?s?|"
                      r"key ?holders?|brand ambassadors?|fitting room|team members?|crew members?|stylists?|beauty advisors?|"
                      r"concierge|front desk(?: \w+)?|receptionists?"),
    # warehouse / logistics / drivers / purchasing
    (OUT, None, None, r"warehouse(?: \w+)?(?: \w+)?|forklift(?: \w+)?|drivers?|delivery (?:driver|associate|helper)s?|couriers?|"
                      r"pickers?|packers?|material handlers?|shipping(?: and receiving)?(?: \w+)?|receiving (?:clerk|associate)s?|"
                      r"freight(?: \w+)?|logistics (?:\w+ )?(?:coordinator|specialist|manager|analyst|associate|lead|planner)s?|"
                      r"supply chain (?:\w+ )?(?:manager|analyst|planner|specialist|coordinator|lead|director)s?|"
                      r"inventory (?:\w+ )?(?:specialist|clerk|control|analyst|associate|coordinator|manager)s?|"
                      r"order (?:fulfillment|picker|selector|entry)(?: \w+)?|dispatchers?|truck\w*|cdl|"
                      r"fulfillment (?:\w+ )?(?:associate|operations|specialist|lead|manager|operations lead)s?|"
                      r"purchasing(?: \w+)?|procurement (?:\w+ )?(?:manager|specialist|analyst|coordinator|lead)s?|buyers?|"
                      r"stock(?: \w+)?(?: and)?(?: fulfillment)?|fulfillment(?: \w+)?|mail ?room(?: \w+)?|mail (?:clerk|carrier)s?|loaders?|unloaders?|yard (?:jockey|driver)s?"),
    # sales / business development / client
    (OUT, None, None, r"sales(?: \w+)?(?: \w+)?(?: (?:representative|rep|executive|manager|director|lead|specialist|consultant|"
                      r"agent|associate|engineer|development|partner|leader|advisor|trainer))?s?|"
                      r"account (?:executive|manager|director|representative|coordinator|specialist)s?|bdrs?|sdrs?|"
                      r"business development(?: \w+)?|client (?:partner|executive|advisor)s?|(?:brand )?partnerships? (?:manager|lead|director)s?|"
                      r"acquisition (?:manager|specialist)s?|customer success(?: \w+)?|relationship managers?|"
                      r"real estate(?: \w+)?(?: \w+)?(?: agent)?|agents?|insurance (?:\w+ )?(?:agent|producer|advisor)s?|"
                      r"loan officers?|mortgage(?: \w+)?|telemarketers?|canvassers?"),
    # medical / clinical / pharma / lab science
    (OUT, None, None, r"nurses?|nursing(?: \w+)?|rns?|lpns?|lvns?|cnas?|np|nurse practitioners?|physicians?|doctors?|"
                      r"physician assistants?|medical (?:\w+ )?(?:assistant|billing|biller|coder|coding|receptionist|technologist|"
                      r"scribe|director|science liaison|writer|records|secretary|office)s?|"
                      r"clinical (?:\w+ )?(?:research|coordinator|specialist|nurse|trial|associate|assistant|manager|director|"
                      r"pharmacist|educator|lead|monitor|scientist|documentation)s?|pharmacists?|pharmacy(?: \w+)?|"
                      r"phlebotom\w+|dental(?: \w+)?|dentists?|hygienists?|therapists?|therapy(?: \w+)?|"
                      r"patient (?:care|services|access|intake|coordinator|representative|advocate|transport\w*|sitter|navigator|registration|"
                      r"financial|experience|scheduler|liaison|relations)(?: \w+)?|caregivers?|home health(?: \w+)?|(?:health|personal care) aides?|surgical(?: \w+)?|"
                      r"radiolog\w+(?: \w+)?|sonographers?|veterinar\w+|counselors?|psychologists?|social workers?|"
                      r"case managers?|care (?:manager|coordinator)s?|dietitians?|paramedics?|emts?|"
                      r"chemists?|biologists?|microbiolog\w*|biochemists?|toxicolog\w*|lab(?:oratory)? (?:\w+ )?"
                      r"(?:technician|tech|assistant|analyst|scientist|manager|associate|coordinator|supervisor)s?|"
                      r"qc (?:\w+ )?(?:analyst|inspector|chemist|technician|associate|specialist|lead|manager|reviewer)s?|qc|qa qc|"
                      r"bioprocess(?: \w+)?|cell culture|cell biology|antibody|formulation(?: \w+)?|regulatory affairs(?: \w+)?|"
                      r"(?:scientist|research associate)s? (?:\w+ )?(?:antibody|cell|biology|chemistry|discovery|protein|assay)\w*|"
                      r"deviation(?: and)? capa(?: \w+)?|capa (?:\w+ )?(?:specialist|investigator)s?|aseptic(?: \w+)?|"
                      r"cell line development(?: \w+)?|research associates?"),
    # finance / accounting / insurance ops
    (OUT, None, None, r"accountants?|accounting(?: \w+)?(?: \w+)?|bookkeep\w+|payroll(?: \w+)?|accounts? (?:payable|receivable)(?: \w+)?|"
                      r"financial (?:\w+ )?(?:analyst|advisor|planner|manager|controller|specialist|reporting)s?|"
                      r"finance (?:\w+ )?(?:manager|analyst|director|associate|specialist|lead|partner)s?|controllers?|"
                      r"auditors?|audit (?:associate|manager|senior)s?|tax (?:\w+ )?(?:analyst|manager|preparer|associate|specialist|accountant)s?|"
                      r"treasury(?: \w+)?|credit (?:analyst|manager)s?|underwriters?|underwriting(?: \w+)?|billing (?:specialist|clerk|coordinator|analyst)s?|"
                      r"claims(?: \w+)?(?: \w+)?|collections?(?: \w+)?|fp and a|actuar\w+|bank tellers?|tellers?|bankers?|"
                      r"investment (?:\w+ )?(?:analyst|banker|associate|manager)s?|portfolio managers?|traders?|"
                      r"quantitative (?:risk|analyst)(?: \w+)?|risk (?:analyst|manager|specialist)s?|cost (?:analyst|accountant)s?|"
                      r"verification of benefits(?: \w+)?|title (?:specialist|examiner|officer|processor)s?|escrow(?: \w+)?"),
    # HR / recruiting / training
    (OUT, None, None, r"recruiters?|recruiting(?: \w+)?(?: \w+)?|recruitment(?: \w+)?|talent (?:acquisition|attraction|sourcer|partner|scout|advisor)(?: \w+)?|"
                      r"sourcers?|sourcing (?:specialist|partner)s?|hr(?: \w+)?(?: (?:manager|generalist|partner|business partner|coordinator|"
                      r"specialist|assistant|director|advisor|associate|lead|analyst|administrator))?|human resources(?: \w+)?(?: \w+)?|"
                      r"hrbps?|benefits? (?:\w+ )?(?:analyst|specialist|administrator|coordinator|manager)s?|"
                      r"compensation (?:\w+ )?(?:analyst|specialist|manager|partner)s?|people (?:operations|partner|business partner)(?: \w+)?|"
                      r"workers comp\w*(?: \w+)?|onboarding (?:specialist|coordinator)s?|training (?:\w+ )?(?:specialist|coordinator|"
                      r"manager|developer|facilitator)s?|trainers?|instructors?|teachers?|tutors?|professors?|"
                      r"student (?:advisor|success|services)(?: \w+)?|academic(?: \w+)?|curriculum(?: \w+)?|instructional designers?|"
                      r"quality and training(?: \w+)?"),
    # legal / compliance
    (OUT, None, None, r"attorneys?|lawyers?|paralegals?|legal(?: \w+)?(?: \w+)?|counsel|general counsel|"
                      r"contracts? (?:manager|administrator|specialist|negotiator)s?|compliance (?:\w+ )?(?:analyst|specialist|officer|manager|"
                      r"associate)s?|regulatory compliance(?: \w+)?|regulatory (?:specialist|associate)s?|privacy counsel"),
    # marketing / comms / media
    (OUT, None, None, r"marketing(?: \w+)?(?: \w+)?|content (?:marketing|writer|creator|strategist|manager|moderator|specialist)s?|"
                      r"copywriters?|social media(?: \w+)?|seo (?:specialist|manager|analyst)s?|brand (?:manager|marketing|strategist|designer)s?|"
                      r"public relations(?: \w+)?|pr (?:manager|specialist)s?|communications? (?:\w+ )?(?:specialist|manager|director|coordinator|lead)s?|"
                      r"events? (?:\w+ )?(?:coordinator|manager|planner|specialist)s?|graphic designers?|video editors?|videographers?|"
                      r"photographers?|campaign managers?|community managers?|editors?|journalists?|writers?|"
                      r"influencer(?: \w+)?|creative directors?|art directors?|interior designers?|fashion designers?|"
                      r"measurement partners?|data annotators?|annotators?|data (?:entry|labelers?|collectors?|understanding)(?: \w+)?(?: \w+)?|"
                      r"ai (?:trainer|tutor|rater)s?|raters?|translators?|interpreters?|transcriptionists?"),
    # trades / facilities / non-IT technicians / operators
    (OUT, None, None, r"electricians?|plumbers?|plumbing(?: \w+)?|hvac(?: \w+)?(?: \w+)?|welders?|welding(?: \w+)?|mechanics?|carpenters?|"
                      r"painters?|machinists?|millwrights?|pipefitters?|boilermakers?|masons?|roofers?|laborers?|"
                      r"(?:maintenance|manufacturing|production|electrical|electronics|mechanical|facilities|facility|field service|"
                      r"automotive|aviation|avionics|aircraft|quality|cqa|engineering|eng|lab|wind|solar|power up|process|"
                      r"calibration|instrumentation|biomedical|equipment|industrial|chemical|environmental|maintenance|"
                      r"diesel|elevator|fire alarm|security systems|low voltage|utility|substation|meter|line|"
                      r"cable|fiber splicer|installation|repair|service|appliance|pest control) (?:\w+ )?(?:technician|tech|mechanic|installer|operator)s?|"
                      r"(?:maintenance|facilities|facility|janitor\w*|custodian\w*|groundskeep\w*|porter)(?: \w+)?|"
                      r"(?:machine|equipment|forklift|production|plant|crane|heavy equipment|cnc|drone flight service|process) operators?|"
                      r"assemblers?|assembly (?:technician|worker|associate|operator)s?|fabricators?|inspectors?|"
                      r"(?:solar|cable|satellite|security) installers?|installers?|field installation(?: \w+)?|"
                      r"security (?:guard|officer|agent|patrol|screener|supervisor|specialist ii)s?|guards?|loss prevention(?: \w+)?|"
                      r"production (?:associate|worker|supervisor|manager|planner|scheduler)s?|"
                      r"(?:project|construction) (?:scheduler|controls?|control specialist|superintendent|estimator)s?|"
                      r"project controls?(?: \w+)?|schedulers?|estimators?|surveyors?|drafters?|draftsman|cad (?:designer|drafter|technician|operator)s?|"
                      r"bim (?:modeler|modeller|coordinator|manager|specialist)s?|superintendents?|foreman|foremen|"
                      r"construction(?: \w+)?(?: \w+)?|commissioning(?: \w+)?(?: \w+)?"),
    # mechanical / civil / process / manufacturing / power engineering
    (OUT, None, None, r"(?:mechanical|civil|structural|process|chemical|manufacturing|industrial|controls?|plc|piping|geotechnical|"
                      r"environmental|packaging|quality(?! assurance)|supplier quality|supplier development quality|program quality|"
                      r"reliability and maintenance|maintenance|project|facilities|facility|hvac|plumbing|fire protection|"
                      r"power|power systems|protection|transmission|distribution|substation|utility|energy|nuclear|"
                      r"aerospace|propulsion|thermal|structures|stress|materials|metallurgical|mining|petroleum|"
                      r"reservoir|drilling|biomedical|medical device|mechatronics|tooling|mold|welding|safety|"
                      r"ehs|hse|environmental health and safety|sustainability|traffic|transportation|water|wastewater|"
                      r"layout|factory|plant|production|field service|launch support|cost|estimating|design release|"
                      r"product development|npi|r and d|costing) (?:\w+ )?(?:engineer|engineering|designer|design engineer)s?|"
                      r"distribution (?:designer|engineering)(?: \w+)?|electrical (?:designer|drafter)s?|"
                      r"ehs(?: \w+)?|hse(?: \w+)?|environmental health and safety(?: \w+)?|safety (?:\w+ )?(?:specialist|manager|coordinator|"
                      r"advisor|officer|lead)s?|sustainability(?: \w+)?|cnc(?: \w+)?|plc(?: \w+)?|machining(?: \w+)?"),
    # customer service / admin / clerical / misc
    (OUT, None, None, r"customer (?:service|support|care|experience|relations)(?: \w+)?(?: \w+)?|call center(?: \w+)?|"
                      r"contact center (?:agent|representative|associate)s?|service delivery representatives?|"
                      r"client (?:service|services|support) (?:representative|associate|specialist)s?|"
                      r"(?:administrative|admin|executive|office|personal|legal|planning|program|project) assistants?|"
                      r"office (?:manager|coordinator|administrator|clerk)s?|clerks?|clerical(?: \w+)?|secretar\w+|"
                      r"order entry(?: \w+)?|data entry(?: \w+)?(?: \w+)?|scanning(?: \w+)?|file clerks?|records (?:clerk|specialist)s?|"
                      r"workers compensation administrators?|operations (?:associate|assistant|clerk|coordinator)s?|"
                      r"chauffeurs?|nannies|nanny|babysitters?|pet (?:sitter|groomer)s?|groomers?|lifeguards?|"
                      r"fitness(?: \w+)?|personal trainers?|coaches|coach|athletic(?: \w+)?|"
                      r"land developers?|real estate developers?|property (?:developer|manager)s?|business developers?|"
                      r"leadership developers?|talent developers?|course developers?|curriculum developers?|content developers?|"
                      r"training developers?|lululemon|product operations (?:educator|lead|coordinator)s?|"
                      r"account management(?: \w+){0,2}|line engineers?|production line(?: \w+){0,2}|project architects?|job captains?|landscape architects?|"
                      r"architectural (?:designer|drafter|intern|project manager|staff)s?|(?:healthcare|building|interior) (?:project )?architects?|"
                      r"provider (?:network|data|enrollment|relations)(?: \w+){0,3}|vehicle dynamics(?: \w+){0,2}|cae (?:engineer|analyst)s?|"
                      r"csrs?|linguists?|panelists?|detailers?|crew chiefs?|rodman|rodmen|"
                      r"expeditors?|processors?|servicers?|producers?|planners?|investigators?|case (?:administrator|manager)s?|"
                      r"quality control(?: \w+)?|candidate experience(?: \w+)?|research advisors?|document control(?: \w+)?|"
                      r"(?:member|account|guest|patient|client) (?:\w+ )?(?:service|services|experience) representatives?"),
]

_RULES = [(verdict, cat, lean, re.compile(r"(?<![a-z0-9])(?:" + src + r")(?![a-z0-9])"))
          for verdict, cat, lean, src in _RULES_SRC]

# Unmistakable tech head nouns. Checked first, on the title's main segment: they
# win over non-IT words elsewhere ("Senior R&D Software Engineer", "Application
# Developer-Real Estate & Facilities", "Customer Support Engineer").
_STRONG_IN_SRC: list[tuple[str, str]] = [
    ("software", r"software (?:development )?(?:engineer|developer|programmer|architect)s?|software engineering (?:manager|lead|director)s?|"
                 r"sdes?|sdets?|swes?|member of (?:the )?technical staff|"
                 r"(?:application|applications|web|mobile|ios|android|full stack|fullstack|front end|frontend|back end|backend|"
                 r"api|game|" + _LANG + r") (?:software )?(?:engineer|developer|programmer)s?"),
    ("software", r"(?:consultant|developer|analyst|architect|administrator|admin|engineer|lead|specialist)s? (?:\w+ ){0,1}"
                 r"(?:sap|salesforce|sfdc|servicenow|workday|netsuite|peoplesoft|oracle (?:ebs|fusion|cloud|erp)|dynamics 365|d365)"),
    ("software", r"(?:wms|tms|mes|plm|warehouse (?:management|mgmt) systems?(?: wms)?|manufacturing execution systems?)"
                 r"(?: \w+)? (?:analyst|developer|engineer|consultant|administrator|architect|specialist|lead)s?"),
    ("devops_sre_cloud", r"(?:devops|cloud|platform|site reliability|infrastructure) engineers?"),
    ("data", r"(?:data|analytics|big data|etl|bi) (?:engineer|developer|architect|scientist)s?"),
    ("ml_ai", r"(?:machine learning|ml|ai|deep learning|computer vision|nlp) (?:engineer|developer|scientist|researcher|architect)s?"),
    ("security", r"(?:cyber ?security|information security|application security|cloud security|network security) (?:engineer|analyst|architect)s?"),
    ("embedded_hw", r"(?:firmware|embedded|fpga|asic|rtl) (?:software )?(?:engineer|developer|designer)s?|"
                    r"(?:ic|asic|soc|chip|silicon|pre silicon|post silicon) (?:\w+ )?(?:validation|verification|design|test) engineers?"),
    ("it_support", r"(?:customer|technical|product|application|production|it|software|cloud|platform) support engineers?|"
                   r"application packaging (?:engineer|specialist|analyst)s?|(?:msi|sccm|intune) packag\w* (?:engineer|specialist|analyst)s?"),
    ("security", r"(?:data|information|it|cyber|network|cloud|application|identity) security (?:\w+ ){0,3}"
                 r"(?:analyst|engineer|specialist|architect|administrator|consultant)s?"),
    ("software", r"forward deployed (?:software )?engineers?"),
    ("tech_writing", r"tech writers?|technical writers?"),
    ("design_ux", r"design systems? (?:designer|engineer|lead|manager|architect)s?"),
    ("software", r"(?:solutions?|technical|cloud|software|saas|security|data|network|platform) sales engineers?|"
                 r"(?:technical|technology|software|it|data|cyber ?security|developer) interns?|"
                 r"(?:technical|software|it|data|engineering) (?:co op|coop|internship)s?"),
    ("product_program", r"(?:product|program|project) managers? (?:\w+ ){0,1}(?:developer|developers|api|apis|platform|sdk|data|ai|ml|cloud|infrastructure|devops)"
                        r"(?: (?:experience|tools|platform|products?))?"),
]
_STRONG_IN = [(cat, re.compile(r"(?<![a-z0-9])(?:" + src + r")(?![a-z0-9])")) for cat, src in _STRONG_IN_SRC]
# Patterns whose qualifier often sits in a later segment ("Product Manager,
# Developer Experience", "Warehouse Mgmt. Systems (WMS) Analyst") also run on the full title.
_STRONG_IN_FULL = [_STRONG_IN[2], _STRONG_IN[-1]]


# Technical Account Managers are IT only with tech context (user decision
# 2026-09-30): a tech area / vendor in the title, else the department decides.
_TAM = re.compile(r"(?<![a-z0-9])(?:technical account (?:manager|lead|director|executive)s?|tams?)(?![a-z0-9])")
_TAM_TECH = re.compile(r"(?<![a-z0-9])(?:cloud|software|saas|platform|data|security|cyber|network|networking|infrastructure|"
                       r"it|api|apis|enterprise software|developer|devops|observability|database|analytics|ai|ml|"
                       r"aws|amazon web services|azure|gcp|google cloud|salesforce|servicenow|service now|sap|oracle|"
                       r"microsoft|datadog|snowflake|confluent|databricks|mongodb|elastic|splunk|okta|cisco|vmware|"
                       r"red hat|redhat|atlassian|github|gitlab|hashicorp|cloudflare|twilio|zscaler|palo alto|crowdstrike)(?![a-z0-9])")


# Departments that make a context-free TAM technical.
_TAM_DEPT = re.compile(r"(?<![a-z0-9])(?:engineering|it|information technology|technology|tech|customer success|customer support|"
                       r"technical support|support|professional services|solutions?|services|cloud|product)(?![a-z0-9])")


_TAM_NEUTRAL = frozenset("""senior sr junior jr lead principal staff associate chief head group global regional strategic key
    enterprise named major mid market midmarket smb commercial public sector federal m f x d w h all genders i ii iii iv v vi
    level l1 l2 l3 l4 l5 remote hybrid onsite on site full time part time contract temporary fixed term
    us usa uk emea apac apj amer americas na latam anz dach nordics east west north south central
    new york london singapore sydney tokyo berlin paris toronto dublin austin seattle chicago san francisco
    a an the and of for in to with at team""".split())


def _tam_verdict(full: str) -> Optional[tuple]:
    """None when the title isn't a TAM; else a _decide_title result."""
    m = _TAM.search(full)
    if not m:
        return None
    rest = full[:m.start()] + " " + full[m.end():]
    if _TAM_TECH.search(rest):
        return True, "software", "title", None
    if _NON_IT_QUALIFIER.search(rest):
        return False, None, "qualifier_out", None
    # Any other topic word without a tech one ("- Cranes", "- Life Science") means
    # a non-tech product domain; seniority / level / region words don't count.
    if any(w not in _TAM_NEUTRAL and not w.isdigit() for w in rest.split()):
        return False, None, "qualifier_out", None
    return None, "software", "ambiguous", None  # no lean: department / board context decides


def _strong_in(primary: str, full: str) -> Optional[str]:
    for cat, rx in _STRONG_IN:
        if rx.search(primary):
            return cat
    for cat, rx in _STRONG_IN_FULL:
        if rx.search(full):
            return cat
    return None

# Qualifiers that settle an ambiguous role word, with a category hint for the IT ones.
_IT_QUALIFIERS: list[tuple[str, re.Pattern]] = [(cat, re.compile(r"(?<![a-z0-9])(?:" + src + r")(?![a-z0-9])")) for cat, src in (
    ("software", r"martech|plm|ats|software|sw|application|applications|app|apps|web|mobile|ios|android|api|apis|saas|digital|"
                 r"frontend|front end|backend|back end|full stack|fullstack|microservices?|" + _LANG + "|" + _ERP),
    ("devops_sre_cloud", r"cloud|aws|azure|gcp|devops|github|gitlab|release|deployment|datacenter|sso|cribl|logging|kubernetes|k8s|docker|terraform|infrastructure|platform|sre|ci cd|"
                         r"openshift|ansible|linux"),
    ("data", r"gis|data|analytics|bi|etl|sql|database|warehouse|reporting|power bi|tableau|snowflake|databricks|big data"),
    ("ml_ai", r"deepmind|algorithm|algo|ai|ml|machine learning|llm|genai|artificial intelligence|nlp|computer vision"),
    ("security", r"soar|security|cyber|cybersecurity|infosec|iam|identity|soc|siem|firewall|vulnerability|zero trust|"
                 r"penetration|appsec|grc|tssci|ts sci"),
    ("network_systems_dba", r"exchange online|network|networking|systems administration|sysadmin|windows|unix|vmware|citrix|storage|"
                            r"server|servers|voip|telecom|telecommunications|dba|m365|office 365|o365|endpoint|"
                            r"active directory|data center|noc|mainframe|monitoring|wan|lan|wireless|packet core"),
    ("qa", r"test automation|testing|selenium|sdet|uat|quality assurance software"),
    ("it_support", r"it|information technology|help ?desk|service ?desk|desktop|computer|computers|pc|hardware refresh|"
                   r"technical support|end user|itsm|itil|technology|tech|technical"),
    ("embedded_hw", r"radio frequency|emulation|embedded|firmware|fpga|asic|electronics|electronic|pcb|circuit|circuits|analog|"
                    r"silicon|rf|hardware|iot|vlsi|verilog|vhdl"),
    ("product_program", r"agile|scrum|product|sdlc|jira|kanban|safe"),
    ("design_ux", r"ux|ui|user experience|figma"),
)]

_NON_IT_QUALIFIER = re.compile(r"(?<![a-z0-9])(?:" + "|".join((
    r"construction", r"clinical", r"manufacturing", r"facilities", r"facility", r"marketing", r"finance", r"financial",
    r"accounting", r"hr", r"human resources", r"retail", r"store", r"mechanical", r"civil", r"structural", r"plant",
    r"qc", r"quality", r"supply chain", r"logistics", r"warehouse", r"real estate", r"medical", r"pharma",
    r"pharmaceutical", r"lab", r"laboratory", r"bioprocess", r"biotech", r"radar", r"sar", r"payload", r"mission",
    r"spacecraft", r"satellite", r"propulsion", r"launch", r"factory", r"production", r"process", r"chemical",
    r"environmental", r"safety", r"ehs", r"hse", r"change management", r"risk", r"quantitative", r"maintenance",
    r"hvac", r"power", r"utility", r"utilities", r"distribution", r"energy", r"oil", r"gas", r"mining",
    r"public works", r"controls", r"instrumentation", r"cad", r"bim", r"piping", r"packaging", r"sales",
    r"legal", r"compliance", r"regulatory", r"nursing", r"patient", r"restaurant", r"hospitality", r"closures",
    r"antibody", r"cell", r"assay", r"chemistry", r"biology", r"scientific", r"research and development",
    r"aerospace", r"avionics", r"airframe", r"vehicle", r"automotive", r"rail", r"transit", r"traffic",
    r"water", r"wastewater", r"solar", r"wind", r"nuclear", r"electrical", r"layout", r"tooling", r"welding",
    r"validation", r"sterility", r"microbiology", r"formulation", r"gmp", r"capa", r"deviation", r"food",
    r"beverage", r"nutrition", r"textile", r"apparel", r"footwear", r"merchandise", r"design release",
    r"benefits", r"payroll", r"tax", r"audit", r"insurance", r"claims", r"underwriting", r"banking",
    r"events", r"fitness", r"education", r"curriculum", r"student", r"school", r"teaching",
    r"cable", r"fiber", r"cabling", r"field", r"install", r"installation", r"subassembly", r"talent", r"recruiting",
    r"recall", r"vehicle dynamics", r"cae", r"job captain", r"building", r"healthcare architecture",
    r"client", r"clients", r"agency", r"media", r"audience", r"consumer", r"insights", r"wealth", r"aml", r"kyc",
    r"trade", r"contract", r"sourcing", r"grant", r"community", r"employee relations", r"organizational development",
    r"grievance", r"provider", r"omnichannel", r"study", r"front office", r"mep", r"sprinkler", r"thermal",
    r"materials", r"material", r"assembly", r"equipment", r"new model", r"pharmacy", r"intake", r"aseptic",
    r"business solutions", r"creative", r"design studio", r"onboarding", r"experience",
)) + r")(?![a-z0-9])")

_IT_CONTEXT = re.compile(r"(?<![a-z0-9])(?:" + "|".join((
    r"information technology", r"it", r"software", r"technology", r"technical", r"tech", r"computer", r"data",
    r"cloud", r"devops", r"cyber", r"cybersecurity", r"information security", r"infosec", r"network", r"networking",
    r"developer", r"development", r"programming", r"engineering software", r"digital", r"web", r"mobile",
    r"analytics", r"database", r"infrastructure", r"systems", r"telecom", r"telecommunications", r"erp", r"crm",
    r"saas", r"ai", r"machine learning", r"ml", r"help ?desk", r"service ?desk", r"qa", r"testing", r"ux", r"ui",
    r"product management", r"product", r"platform", r"electronics", r"embedded", r"firmware", r"semiconductor",
    r"security engineering", r"it services", r"application", r"applications", r"internet",
)) + r")(?![a-z0-9])")
_NON_IT_CONTEXT = re.compile(r"(?<![a-z0-9])(?:" + "|".join((
    r"manufacturing", r"mechanical", r"healthcare", r"health care", r"clinical", r"nursing", r"medical",
    r"finance", r"financial", r"accounting", r"human resources", r"hr", r"people", r"retail", r"store", r"stores",
    r"warehouse", r"logistics", r"distribution center", r"supply chain", r"sales", r"marketing", r"legal",
    r"construction", r"facilities", r"scientific", r"science", r"life sciences", r"lab", r"laboratory",
    r"pharmaceutical", r"biotech", r"customer service", r"customer support", r"call center", r"administrative",
    r"office", r"hospitality", r"food", r"restaurant", r"education", r"government services", r"civil",
    r"architecture and engineering", r"energy", r"utilities", r"power", r"aerospace", r"automotive",
    r"industrial", r"skilled trades", r"trades", r"maintenance", r"production", r"quality", r"real estate",
    r"insurance", r"banking", r"creative", r"design and media", r"light industrial", r"transportation",
    r"environmental", r"oil and gas", r"mining", r"chemical", r"electrical", r"engineering and manufacturing",
)) + r")(?![a-z0-9])")

TECH_SKILLS = frozenset((
    "python", "java", "javascript", "typescript", "react", "angular", "vue", "node", "node.js", "nodejs", "go",
    "golang", "rust", "c#", ".net", "dotnet", "c++", "scala", "kotlin", "swift", "php", "ruby", "sql",
    "postgresql", "postgres", "mysql", "oracle", "mongodb", "redis", "kafka", "spark", "hadoop", "airflow",
    "snowflake", "databricks", "dbt", "tableau", "power bi", "aws", "azure", "gcp", "kubernetes", "k8s", "docker",
    "terraform", "ansible", "jenkins", "linux", "salesforce", "servicenow", "sap", "workday", "peoplesoft",
    "mainframe", "cobol", "selenium", "cypress", "machine learning", "pytorch", "tensorflow", "llm", "etl",
    "informatica", "splunk", "devops", "sre", "microservices", "spring", "spring boot", "django", "flask",
    "fastapi", "graphql", "rest", "ios", "android", "figma", "jira", "cissp", "sailpoint", "okta", "cyberark",
    "cisco", "vmware", "active directory", "sccm", "intune", "citrix", "firewall", "ci/cd", "git", "html", "css",
    "api", "apis", "sql server", "t-sql", "pl/sql", "unix", "bash", "powershell", "networking", "tcp/ip",
    "fpga", "verilog", "vhdl", "embedded", "firmware", "rtos", "matlab", "sas", "r", "excel vba", "vba",
))


def _ctx_verdict(text: Optional[str]) -> Optional[bool]:
    if not text:
        return None
    n = _norm(text if isinstance(text, str) else " ".join(str(t) for t in text if t))
    it_hits = len(_IT_CONTEXT.findall(n))
    non_hits = len(_NON_IT_CONTEXT.findall(n))
    if it_hits > non_hits:
        return True
    if non_hits > it_hits:
        return False
    return None


def tech_skill_count(skills: Optional[Iterable[str]]) -> int:
    if not skills:
        return 0
    if isinstance(skills, str):
        skills = re.split(r"[,;|]", skills)
    return sum(1 for s in skills if s and str(s).strip().lower() in TECH_SKILLS)


def _best(text: str):
    """Rule match that ends last (ties: the longer one) -> (verdict, category, lean, start, end)."""
    best = None
    for verdict, cat, lean, rx in _RULES:
        for m in rx.finditer(text):
            key = (m.end(), m.end() - m.start(), verdict != AMB)
            if best is None or key > best[0]:
                best = (key, (verdict, cat, lean, m.start(), m.end()))
    return best[1] if best else None


def _it_qualifier(text: str, exclude: tuple[int, int]) -> tuple[int, Optional[str]]:
    """IT qualifier hits outside the ambiguous phrase -> (count, first category)."""
    hits, first = 0, None
    for cat, rx in _IT_QUALIFIERS:
        for m in rx.finditer(text):
            if exclude[0] <= m.start() < exclude[1]:
                continue
            hits += 1
            if first is None:
                first = cat
            break
    return hits, first


def _non_it_qualifier(text: str, exclude: tuple[int, int]) -> int:
    return sum(1 for m in _NON_IT_QUALIFIER.finditer(text) if not (exclude[0] <= m.start() < exclude[1]))


def _in_category(text: str) -> Optional[str]:
    """Category of the latest explicit IT phrase in text (used as a hint)."""
    best = None
    for verdict, cat, lean, rx in _RULES:
        if verdict != IN:
            continue
        for m in rx.finditer(text):
            key = (m.end(), m.end() - m.start())
            if best is None or key > best[0]:
                best = (key, cat)
    return best[1] if best else None


@lru_cache(maxsize=20000)
def _decide_title(title: str) -> tuple[Optional[bool], Optional[str], str, Optional[bool]]:
    """(is_it | None, category, reason, lean) from the title alone."""
    full = _norm(title)
    if not full.strip():
        return None, None, "no_match", None
    primary = _norm(_SEGMENT_SPLIT.split(str(title), maxsplit=1)[0])
    tam = _tam_verdict(full)
    if tam is not None:
        return tam
    strong = _strong_in(primary if primary.strip() else full, full)
    if strong:
        return True, strong, "title", None
    for text in ((primary, full) if primary.strip() and primary != full else (full,)):
        hit = _best(text)
        if hit is None:
            continue
        verdict, cat, lean, start, end = hit
        if verdict == AMB:
            # "Site Reliability Engineer", "Firmware Engineer": an explicit IT phrase
            # overlapping / right before the ambiguous head noun settles it.
            for v2, c2, _l2, rx2 in _RULES:
                if v2 != IN:
                    continue
                for m2 in rx2.finditer(text):
                    if m2.start() < end and m2.end() >= start - 1:
                        return True, c2, "title", None
        if verdict == IN:
            return True, cat, "title", None
        if verdict == OUT:
            return False, None, "title_out", None
        # Ambiguous: qualifiers anywhere in the title (outside the phrase itself).
        span = (start, end) if text is full else (-1, -1)
        if text is not full:
            # map the phrase into the full title so it does not count as its own qualifier
            phrase = text[start:end]
            pos = full.find(phrase)
            span = (pos, pos + len(phrase)) if pos >= 0 else (-1, -1)
        it_hits, it_cat = _it_qualifier(full, span)
        non_hits = _non_it_qualifier(full, span)
        if it_hits > non_hits:
            return True, _in_category(full) or cat if cat else it_cat, "qualifier", None
        if non_hits > it_hits:
            return False, None, "qualifier_out", None
        return None, cat or it_cat, "ambiguous", lean
    return None, None, "no_match", None


def classify_it(title: Optional[str], category: Optional[str] = None, department: Optional[str] = None,
                skills: Optional[Iterable[str]] = None) -> ItDecision:
    """Full decision with the reason (see module doc)."""
    try:
        is_it, cat, reason, lean = _decide_title(str(title or "").strip()[:300])
    except Exception:  # pragma: no cover - never break a save path on a regex issue
        return ItDecision(None, None, "no_match")
    if is_it is not None:
        return ItDecision(is_it, cat, reason)
    # Undecided title (ambiguous word or no role phrase): board category, department, skills.
    if _TAM.search(_norm(title or "")):
        ctx = " ".join(str(c) for c in (category, department) if c)
        if ctx and _TAM_DEPT.search(_norm(ctx)) and not _NON_IT_CONTEXT.search(_norm(ctx)):
            return ItDecision(True, "software", "context")
    for ctx in (category, department):
        v = _ctx_verdict(ctx)
        if v is True:
            return ItDecision(True, cat or "software", "context")
        if v is False:
            return ItDecision(False, None, "context_out")
    if tech_skill_count(skills) >= 2:
        return ItDecision(True, cat or "software", "skills")
    if reason == "ambiguous" and lean is not None:
        return ItDecision(lean, cat if lean else None, "lean" if lean else "lean_out")
    return ItDecision(None, cat, reason)


def is_it_role(title: Optional[str], category: Optional[str] = None, department: Optional[str] = None,
               skills: Optional[Iterable[str]] = None, ambiguous_default: bool = False) -> bool:
    """True when the title is an IT / tech role (undecided titles -> ambiguous_default)."""
    d = classify_it(title, category, department, skills)
    return ambiguous_default if d.is_it is None else d.is_it


def it_category(title: Optional[str], category: Optional[str] = None, department: Optional[str] = None,
                skills: Optional[Iterable[str]] = None, ambiguous_default: bool = False) -> Optional[str]:
    """IT_CATEGORIES code for an IT role, else None."""
    d = classify_it(title, category, department, skills)
    if d.is_it or (d.is_it is None and ambiguous_default):
        return d.category or "software"
    return None
