# Manual work for the CivicEye team

The software cannot do these tasks. Do not record any of them as done without the evidence listed.

## A. Approvals and scope

| Done | Task | Reason | Timing | Required evidence |
|---|---|---|---|---|
| [ ] | Confirm project title, guide, team names, USNs and approved scope | Synopsis and reports need verified details | Before synopsis submission | Signed/approved synopsis |
| [ ] | Obtain permission for community engagement, photography and video collection | Legal and ethical collection of local data | Before any field work | Written permission letters |
| [ ] | Select study streets and safe camera viewpoints | Pilot area and traffic views must be fixed and safe | Before data collection | Map of area, viewpoint photos, guide sign-off |
| [ ] | Confirm reviewers/officers are simulated unless officially authorised | Avoid implying a municipal partnership | Before demo/pilot | Note in report; authorisation letter if any |

## B. Community work

| Done | Task | Reason | Timing | Required evidence |
|---|---|---|---|---|
| [ ] | Get guide approval for the consent text (see `/privacy`) and questionnaire | Ethical data collection | Before survey | Approved documents |
| [ ] | Recruit consenting participants | Survey and usability testing | Before survey | Signed/recorded consent |
| [ ] | Conduct the proposed 30–50 person needs survey | Evidence of community need | Early in project | Raw responses (anonymised), summary |
| [ ] | Conduct one awareness session and one hands-on demonstration | Community project requirement | Mid project | Attendance, dated photos with permission |
| [ ] | Recruit at least 15 usability participants where feasible | Usability evaluation | After phase 2 | Task results, SUS or similar forms |
| [ ] | Collect real feedback, never fabricated | Academic honesty | Throughout | In-app feedback export, forms |
| [ ] | Keep permission-appropriate evidence of activities | Report and viva | Throughout | Folder of dated evidence |

## C. Data

| Done | Task | Reason | Timing | Required evidence |
|---|---|---|---|---|
| [ ] | Check RDD2022 and TACO licences and download them manually | Licences must allow academic use; no redistribution | Before phase 2 | Licence text saved, download date |
| [ ] | Collect lawful, safe local images and videos | Local test set | After permissions | Collection log |
| [ ] | Avoid identifiable people and number plates | Privacy | During collection | Review checklist |
| [ ] | Annotate and cross-review local data | Ground truth for evaluation | Before evaluation | Annotation files, reviewer names |
| [ ] | Manually count vehicles for reference intervals | Traffic count evaluation | Phase 3 | Count sheets per interval |
| [ ] | Identify true duplicate and nearby-but-distinct report pairs | Duplicate detection test set | Phase 2 | Labelled pair list |
| [ ] | Independently review risk and priority examples | Check that priority makes sense | Phase 2 | Two reviewers' ratings, disagreements noted |

## D. Models

| Done | Task | Reason | Timing | Required evidence |
|---|---|---|---|---|
| [ ] | Provide compute (GPU or Colab) where training needs it | CPU training is slow | Phase 2 | Hardware details |
| [ ] | Run training if it cannot be run in the dev environment | Weights are not shipped | Phase 2 | Training logs, seed, config |
| [ ] | Inspect model errors | Understand failure cases | After evaluation | Error example sheet |
| [ ] | Review local test-set performance | Real-world validity | After evaluation | Metrics table with sample sizes |
| [ ] | Decide whether each trained feature is good enough to advertise | Avoid overclaiming | Before pilot | Team/guide decision note |

## E. Deployment

| Done | Task | Reason | Timing | Required evidence |
|---|---|---|---|---|
| [ ] | Provide real secrets only through `.env`/environment | Security | Any deployment | No secrets in git |
| [ ] | Configure hosting, HTTPS, storage, backups and retention if deployed publicly | Security and privacy | Before public pilot | Deployment notes |
| [ ] | Review map tile provider terms and attribution | OSM tile policy | Before public pilot | Policy check note |
| [ ] | Test on real phones and browsers (geolocation, camera upload, map) | Not tested yet | Before demo/pilot | Test log with devices |
| [ ] | Get permission before any government system integration | Out of scope without approval | If ever needed | Written approval |
| [ ] | Do not buy services or create accounts automatically | Budget and approvals | Always | — |

## F. Academic submission

| Done | Task | Reason | Timing | Required evidence |
|---|---|---|---|---|
| [ ] | Enter actual survey results, metrics, activity dates, costs and limitations | Report accuracy | Final report | Source data |
| [ ] | Verify every reference | No invented citations | Before submission | Checked bibliography |
| [ ] | Add approved screenshots and photos | Report and slides | Final report | Permission for any people shown |
| [ ] | Prepare synopsis, report, slides and viva explanation | Submission | As scheduled | Documents |
| [ ] | Do not claim repairs, accident reduction or congestion reduction without evidence | Academic honesty | Always | — |
