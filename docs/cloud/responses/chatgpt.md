AgriGate: cloud video production architecture
Research baseline: 22 November 2026. The design below preserves the supplied pipeline, including its three mandatory approvals, multiple narration takes, per-shot image retries, SHA-1-bound visual inspection, and episode.json as the contract between stages.

One important correction from the current documentation: Remotion does not automatically require a paid company licence for every commercial user. Its current pricing page offers a free licence to individuals and companies of up to three people, subject to eligibility terms. The separate Automators plan is aimed at products that provide automated video creation and has a $100/month minimum. AgriGate should check its eligibility rather than assume either charge applies. 

Remotion+1

A. Summary recommendation
1. Keep the control plane, workflow, database, storage, identity, dashboard and rendering on AWS, using Mumbai (ap-south-1) as the primary region.
2. Use AWS Step Functions Standard as the durable workflow engine. Its one-year execution and callback capabilities suit approvals that may wait days. 
   
   AWS Step Functions+1
3. Run ordinary Python stages as Lambda functions or ECS/Fargate tasks; run CUDA workloads in AWS Batch managed EC2 GPU compute environments, with capacity scaling to zero.
4. Start GPU porting with an L4-class worker for TTS and Whisper. Benchmark image generation separately; do not assume every image checkpoint fits a 24 GB GPU.
5. Keep Claude responsible for script drafting, visual inspection and review. Use the Anthropic API for bounded judgement tasks and an isolated Claude Agent SDK container for interactive operator sessions.
6. Put immutable artefacts in S3, workflow and approval metadata in DynamoDB, and use a single-writer merge step to publish validated episode.json revisions.
7. Enforce approvals with separate Cognito operator and approver roles. Agents and workers must not possess the authority to approve.
8. Use Remotion Lambda for the current short renders, subject to testing the 15-minute Lambda execution ceiling; use a container render fallback for heavier future work.
9. At this volume, avoid an always-on GPU, Kubernetes, or a permanently running orchestration server.
10. Treat model parity, licences, image-inspection reliability and GPU availability as deployment gates—not assumptions.
B. Architecture diagram
Recommended topology · AWS Mumbai primary region
#chatgpt-mermaid-_r_b5_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(13, 13, 13);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_b5_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_b5_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_b5_ .error-icon{fill:rgb(243, 243, 243);}#chatgpt-mermaid-_r_b5_ .error-text{fill:rgb(13, 13, 13);stroke:rgb(13, 13, 13);}#chatgpt-mermaid-_r_b5_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_b5_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_b5_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_b5_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_b5_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_b5_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_b5_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_b5_ .marker.cross{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_b5_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-_r_b5_ p{margin:0;}#chatgpt-mermaid-_r_b5_ .label{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_b5_ .cluster-label text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_b5_ .cluster-label span{color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_b5_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_b5_ .label text,#chatgpt-mermaid-_r_b5_ span{fill:rgb(13, 13, 13);color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_b5_ .node rect,#chatgpt-mermaid-_r_b5_ .node circle,#chatgpt-mermaid-_r_b5_ .node ellipse,#chatgpt-mermaid-_r_b5_ .node polygon,#chatgpt-mermaid-_r_b5_ .node path{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_b5_ .rough-node .label text,#chatgpt-mermaid-_r_b5_ .node .label text,#chatgpt-mermaid-_r_b5_ .image-shape .label,#chatgpt-mermaid-_r_b5_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_b5_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_b5_ .rough-node .label,#chatgpt-mermaid-_r_b5_ .node .label,#chatgpt-mermaid-_r_b5_ .image-shape .label,#chatgpt-mermaid-_r_b5_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_b5_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_b5_ .root .anchor path{fill:rgb(143, 143, 143)!important;stroke-width:0;stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_b5_ .arrowheadPath{fill:rgb(143, 143, 143);}#chatgpt-mermaid-_r_b5_ .edgePath .path{stroke:rgb(143, 143, 143);stroke-width:1px;}#chatgpt-mermaid-_r_b5_ .flowchart-link{stroke:rgb(143, 143, 143);fill:none;}#chatgpt-mermaid-_r_b5_ .edgeLabel{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-_r_b5_ .edgeLabel p{background-color:rgb(252, 252, 252);}#chatgpt-mermaid-_r_b5_ .edgeLabel rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_b5_ .labelBkg{background-color:rgba(252, 252, 252, 0.5);}#chatgpt-mermaid-_r_b5_ .cluster rect{fill:rgb(243, 243, 243);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_b5_ .cluster text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_b5_ .cluster span{color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_b5_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:12px;background:rgb(243, 243, 243);border:1px solid rgba(0, 0, 0, 0.1);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_b5_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_b5_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_b5_ .icon-shape,#chatgpt-mermaid-_r_b5_ .image-shape{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-_r_b5_ .icon-shape p,#chatgpt-mermaid-_r_b5_ .image-shape p{background-color:rgb(252, 252, 252);padding:2px;}#chatgpt-mermaid-_r_b5_ .icon-shape .label rect,#chatgpt-mermaid-_r_b5_ .image-shape .label rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_b5_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_b5_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_b5_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_b5_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_b5_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_b5_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_b5_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b5_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_b5_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_b5_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_b5_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b5_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_b5_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_b5_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b5_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_b5_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_b5_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b5_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_b5_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b5_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_b5_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_b5_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_b5_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_b5_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_b5_ .node rect,#chatgpt-mermaid-_r_b5_ .node circle,#chatgpt-mermaid-_r_b5_ .node ellipse,#chatgpt-mermaid-_r_b5_ .node polygon,#chatgpt-mermaid-_r_b5_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_b5_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_b5_ .mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_b5_ .edgePaths .flowchart-link{stroke:rgb(143, 143, 143);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_b5_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_b5_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}Operator / ApproverPhone or desktopControl roomCloudFront + S3 + CognitoAPI GatewayLambda command APIDynamoDBepisode index, revisions,approvalsS3sources, episode.json,media, logsStep Functions StandardSource ingest + scriptLambda / Fargate + Claudeon BedrockNormalize + validateLambda / FargateCheckpoint 1Script approvalAWS Batch GPUMaya / Veena +faster-whisperWord alignment + audioassemblyAWS Batch GPUFLUX.2 Klein 4BClaude vision inspectionFull image + crops + cast refGraphics + cue generationRemotion Lambda540p draftCheckpoint 2Draft reviewRemotion Lambda1080p finalFFmpeg / Pillow QA+ Claude contact-sheetreviewPackage + metadataCheckpoint 3Final approvalManual download orYouTube API uploadPublished / scheduledApproval APIapprover role onlyApprovedFail: save verdict, reviseprompt, retryAll passRejected: scene notesApprovedRejectedApprovedCallback tokenCallback tokenCallback token





The workflow engine carries identifiers and S3 object references, not video/audio/image bytes. Step Functions state input/output is limited to 256 KiB; this design keeps the orchestration payload small and all large artefacts in S3. 

AWS Step Functions+1

C. Service per job
Job	Recommended service	Compute / model	Why and rejected alternative	Estimated marginal cost per long episode
Brief, uploads, source capture	API Gateway + Lambda; S3 presigned uploads	Lambda, no GPU	Lightweight, event-driven; no always-on app server	$0.01–$0.05
Source fetching and script	ECS Fargate task + Bedrock Claude Sonnet 5	2–4 vCPU, 8–16 GiB; in.anthropic.claude-sonnet-5	Can fetch/parse approved source documents and provide bounded agent tools; Bedrock geo inference keeps inference within India	$0.50–$1.50
Text normalize, schema validation, status gates	Lambda	1–2 GiB; Python/Pydantic	Sub-second work and small payloads; use Fargate only for unusually large PDF work	$0.01–$0.05
Narration takes	AWS Batch, EC2 managed GPU environment	g6.2xlarge, NVIDIA L4, 8 vCPU, 32 GiB host RAM; Maya 2 Native / Veena	GPU capacity can scale down to zero; better than a persistent GPU VM	$0.20–$1.20
ASR, take scoring, word timing	Same Batch queue as TTS	L4; faster-whisper large-v3-turbo, FP16 or int8-FP16	Keep audio and ASR close to reduce transfers and simplify worker containers	Included in TTS budget above
Cast references and image generation	AWS Batch, separate GPU queue	g6e.2xlarge, NVIDIA L40S 48 GB; FLUX.2 Klein 4B	More VRAM headroom for image-edit pipelines; one queue can serve cast setup and per-scene attempts	$1.35–$2.70
Mandatory image inspection	Bedrock Claude vision	Sonnet 5, full image + two crops + cast reference	Retains the currently accepted strong-vision gate; do not substitute an open VLM as decider	Included in Claude budget below
Graphics and cue generation	Lambda	CPU only	Pure Python and deterministic timing calculations	Under $0.05
Draft/final rendering	Remotion Lambda	AWS Lambda workers in ap-south-1; Chrome/Remotion	Existing React composition; chunked parallel rendering; ECS fallback for renders exceeding Lambda limits	$0.20–$0.90 for several passes
Technical QA and contact sheets	ECS Fargate task	2–4 vCPU, 8 GiB; FFmpeg/Pillow	Predictable CPU/memory; no GPU needed	$0.05–$0.25
Packaging and metadata	Lambda + Claude Bedrock	Python, Sonnet 5 for text	Small deterministic packaging job	$0.10–$0.50
State, approvals, progress	DynamoDB + Step Functions + API Gateway	Managed services	No database server or workflow daemon to operate	Shared platform overhead
Preview delivery	CloudFront in front of private S3	Signed URLs/cookies	Phone-friendly viewing without exposing raw episode buckets	Shared storage/CDN overhead

GPU sizing and scale behaviour. AWS Batch itself has no additional service charge; compute is billed as EC2 or Fargate. It can schedule GPU resources and scale EC2 capacity to match queued jobs. Use a managed compute environment with minimum vCPUs set to zero, a small maximum, and an On-Demand fallback when Spot capacity is unavailable. 

aws.amazon.com+2

- TTS/Whisper: Start with g6.2xlarge (L4, 8 vCPU, 32 GiB RAM). It gives one GPU worker enough headroom for the current Maya 2 Native inference engine and Whisper without keeping a host running between episodes. Test one model per process at first; do not assume simultaneous TTS and ASR will fit or improve throughput.
- Image generation: Start with g6e.2xlarge (L40S, 48 GB VRAM, 8 vCPU, 64 GiB RAM). FLUX.2 Klein 4B is documented as consumer-GPU-capable, but this is a conservative size for reference-edit workflows, larger resolutions, crops and concurrent inspection/preprocessing. Benchmark g6.2xlarge as a cost-down candidate once the pipeline works. AWS lists G6 and G6e in Mumbai. 
  
  Amazon EC2+3
- Cold starts: expect several minutes, not seconds, for a fresh GPU VM to launch, pull a multi-GB image and load weights. Keep container layers and model weights in regional ECR/S3; avoid downloading Hugging Face weights on every job. A short-lived warm worker can be retained during a production burst, but do not pay for a GPU between episodes.
- Quotas: request EC2 G/accelerated-instance vCPU quota and AWS Batch service quotas before the first parallel run. Keep concurrency modest initially (one audio worker and one image worker), then increase after throughput, VRAM and Spot interruption tests. I would not use 40 simultaneous GPU instances for 40 shots: queue work and run a bounded number of workers.
- Lambda vs GPU: Lambda is for short orchestration and CPU functions, not these CUDA model workers. Its execution ceiling is 15 minutes; longer jobs belong in Batch or ECS. 
  
  AWS Lambda+1
The price figures in the table are planning allowances rather than AWS quotes. The GPU-hour assumptions and monthly roll-up are stated in section I; actual execution time depends on the container, model revision, quantisation, image size and GPU availability.
D. Orchestration, Claude’s role and human checkpoints
Workflow engine: Step Functions Standard
Use one Standard state machine per episode, with nested child workflows for image shots and narration sentences where that makes retries easier to isolate. Standard executions can run for up to one year; Express workflows are limited to five minutes and are therefore inappropriate for the end-to-end episode. 

AWS Step Functions+1

Use:
- Task states for validation, packaging and metadata functions.
- AWS Batch .sync integrations for long-running GPU and FFmpeg jobs.
- Map or Distributed Map for sentence/take and scene/shot fan-out, with explicit MaxConcurrency.
- Retry for infrastructure failures and throttling; Catch for model failures that require human attention or a prompt revision.
- WaitForTaskToken for all three approval pauses.
- A child execution per image attempt or per scene if independent reruns become cumbersome in a single state machine.
The system should fan out the work units, not unbounded GPU capacity. For example, produce all sentence/take job descriptions, let Batch schedule a bounded number of GPU workers, and publish each take result to its own S3 key. A similar pattern applies to 40 shots × up to 3 attempts. Step Functions Map capacity is ample for this pipeline, but service quotas must still be checked in the target account. 

AWS Step Functions

Approval callbacks: the enforcement point
At each checkpoint, the state machine reaches a callback task and pauses. Store its task token encrypted in DynamoDB with the episode ID, checkpoint type, exact artifact revision/hash, expiry and workflow execution ARN. The approval API is the only component allowed to call SendTaskSuccess or SendTaskFailure.

Use three distinct roles:
Role	Can do	Cannot do
Operator	Create episodes, upload sources, start/retry jobs, leave notes, request reruns	Approve a checkpoint or change status directly
Approver	View the presented revision, approve/reject with comments	Edit pipeline artefacts or run model jobs
Agent/worker	Read permitted inputs, write attempt outputs and inspection results	Approve, issue callback success, or set a later status

An approval request should be accepted only if the approver is authenticated and authorised, the decision applies to the exact revision/hash being reviewed, and the task token has not already been consumed. Save user ID, role, decision, timestamp, notes, artifact hash and workflow execution ID as an append-only approval record.

This is the key design rule: the agent cannot approve itself, even if prompted to do so. The agent receives no approval tool, no callback token and no IAM permission to update the approval record or move workflow state. The state machine advances only after the approval API receives a valid human decision. A rejected checkpoint records notes and returns the workflow to the appropriate stage rather than creating a new episode.
Where Claude fits
Use two execution modes, with the same model tools and prompt library:
1. Unattended mode: small, bounded Bedrock Converse calls from workflow tasks for script drafting, prompt critique, image inspection and contact-sheet QA. Each call has a typed JSON output contract, a token/time budget and explicit S3 source references. The workflow—not Claude—decides whether a stage passed its mechanical validation.
2. Interactive mode: launch a short-lived, isolated ECS Fargate task running the Claude Agent SDK for an operator’s active episode. Stream its conversation through the control-room API. Its tools can read the episode workspace, fetch source documents through the source-fetch service, edit permitted draft files and invoke approved stage commands. It cannot access approval APIs or unrestricted AWS credentials.
Claude Code on the web is not the production runtime to build around: it is a hosted coding session, not the durable episode workflow, and it does not fit the same Bedrock-backed regional inference path. The Claude Agent SDK is the better way to embed tool-using, interactive sessions inside your cloud control room. Keep those agent sessions disposable; persist their transcript and useful outputs to S3, not their process state.
The three checkpoints
- CP1 — Script: show the final normalized Hindi narration, scene-by-scene source references, word/length targets and all unresolved [VERIFY] markers. The API must refuse to offer the Approve action if any [VERIFY] remains or a cited source file is missing.
- CP2 — Draft: show the 540p video, per-scene playback and notes, plus the final narration audio. Rejection stores notes against scene IDs and the draft revision. The workflow re-renders only affected scenes/compositions where possible.
- CP3 — Final/package: show 1080p final video, thumbnail, title/description/tags, sources and synthetic-content disclosure. A rejection can return to final render or packaging based on the notes. Only an approval allows the upload task to become eligible.
On phones, the review page should load a small preview first, use signed media URLs, support timestamped notes and expose large Approve/Reject controls. Send notifications when a checkpoint is waiting and when a job fails; SES email is the least complicated first integration. AWS currently lists SES outbound email pricing at $0.10 per 1,000 messages for the standard send path, subject to the selected region and ancillary charges. 

aws.amazon.com+1

E. Data and storage
Storage layout
Keep the episode directory shape, but make S3 the durable filesystem and preserve the existing file names and schema wherever possible. Use a private, versioned bucket such as agrigate-prod-episodes with Block Public Access, SSE-KMS encryption, access logging and lifecycle rules.
s3://agrigate-prod-episodes/
  episodes/<episode_id>/
    brief.md
    sources/
      manifest.json
      <sha256>/<original_filename>.pdf
    script.md
    episode/
      revisions/
        r000001.json
        r000002.json
      current.json                 # optional convenience copy
    audio/
      takes/<sentence_id>/<take_id>/
        audio.wav
        transcript.json
        metrics.json
      selected/<sentence_id>.json
      final/<scene_id>.wav
      word-timings.json
    images/
      <scene_id>/<shot_id>/
        attempts/attempt-001.png
        attempts/attempt-002.png
        crops/attempt-001/
        inspections/attempt-001.json
        selected.json
    graphics/
      props.json
    render/
      draft/<revision_id>/draft.mp4
      final/<revision_id>/video.mp4
      thumbnail.png
    review/
      contactsheets/
      review.md
    package/
      youtube.md
      metadata.json
    logs/
      events/<timestamp>-<event_id>.json
      agent-sessions/<session_id>.jsonl


The source manifest should record, for every document, original URL, retrieval time, publisher, filename, SHA-256, MIME type and any known conflict or supersession note. Keep a separate source cache for official government and ICAR documents. Once a script is drafted, its factual claims must cite the local source IDs—not a transient web search result.
episode.json concurrency: one publisher, many workers
Do not allow GPU workers, Lambda functions and the agent to concurrently edit one shared episode.json. That makes lost updates and non-repeatable state likely.

Instead:
1. The orchestrator reads the current episode revision r000023.json.
2. Each worker writes an immutable, per-item result object: for example, images/scene-08/shot-02/attempts/attempt-003.result.json or audio/takes/sentence-14/take-05/metrics.json.
3. The worker emits a completion event containing only the S3 key, content hash, item ID, job ID and outcome.
4. A single merge/validator task consumes those results, checks the relevant schema and all gates, and constructs a complete new episode snapshot.
5. The merger writes revisions/r000024.json to a unique, immutable S3 key.
6. It then updates the DynamoDB episode pointer with a conditional write: only replace revision 23 with revision 24 if the stored revision is still 23. If that condition fails, reload the latest revision, reconcile, revalidate and publish a new revision.
DynamoDB conditional writes support optimistic locking; S3 conditional requests support If-Match/If-None-Match preconditions. Use both where applicable. The S3 snapshot is the canonical data document; DynamoDB holds the latest pointer and queryable operational state, not a second mutable copy of the episode data. 

Amazon DynamoDB+3

Operational database
A small DynamoDB single-table design is sufficient:
Item	Useful attributes
Episode	episode_id, status, revision, current_json_key, current_json_hash, updated_at
Job	job_id, episode_id, stage, item_id, attempt, state, batch_job_id, started_at, ended_at
Approval	episode_id, checkpoint, revision, artifact_hash, decision, approver_id, timestamp, comments
Event	episode_id, event_id, event_type, timestamp, s3_key, job_id
Lock/lease	episode_id, worker_id, lease_expiry, expected_revision

DynamoDB Streams can feed dashboard updates and notifications, but the append-only event objects in S3 remain the audit trail. Do not expire approvals, source manifests, selected artefacts or inspection decisions with TTL. A TTL can be used for disposable leases, transient notification state and short-lived session metadata.
Versioning and retention
- Keep S3 versioning enabled for the episode and shared-asset buckets. Hash all source and generated media files at write time.
- Retain every generated image attempt, every narration take and every inspection result. The attempt history is part of the reproducibility record, not a cache to be casually deleted.
- Keep final videos, approved scripts, source PDFs, approvals, inspection verdicts and render manifests for a longer policy period—start with 3 years, then align with legal/accounting requirements.
- Use S3 Intelligent-Tiering or lifecycle transitions for infrequently accessed old attempts, after confirming retrieval cost and latency are acceptable. Keep current working artefacts in S3 Standard.
- Serve review previews through CloudFront with signed URLs/cookies. Do not make the origin bucket public. Use S3 presigned uploads for source documents and private outputs for all other artefacts.
The phone-facing review page should request a smaller preview proxy; it should not stream the 400 MB final MP4 just to show the approver a draft.
F. Messaging and event flow
Use Step Functions for the authoritative sequence and AWS Batch/S3 for work execution. Use EventBridge for domain events such as EpisodeCreated, ImageInspectionFailed, DraftRejected and EpisodeApproved; use an SQS queue for independent, retryable work dispatch where decoupling is helpful. Do not have every worker call the next worker directly. The state machine should remain the source of truth for stage order and approval waits.
Episode sequence, including failures and human decisions
QA/FFmpegRemotion LambdaAWS Batch GPUClaude/BedrockStep FunctionsS3DynamoDBAPI/LambdaControl RoomQA/FFmpegRemotion LambdaAWS Batch GPUClaude/BedrockStep FunctionsS3DynamoDBAPI/LambdaControl Room#chatgpt-mermaid-_r_cg_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(13, 13, 13);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_cg_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_cg_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_cg_ .error-icon{fill:rgb(243, 243, 243);}#chatgpt-mermaid-_r_cg_ .error-text{fill:rgb(13, 13, 13);stroke:rgb(13, 13, 13);}#chatgpt-mermaid-_r_cg_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_cg_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_cg_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_cg_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_cg_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_cg_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_cg_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_cg_ .marker.cross{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_cg_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-_r_cg_ p{margin:0;}#chatgpt-mermaid-_r_cg_ .actor{stroke:rgb(83, 154, 248);fill:rgb(222, 234, 251);stroke-width:1;}#chatgpt-mermaid-_r_cg_ rect.actor.outer-path[data-look="neo"]{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_cg_ rect.note[data-look="neo"]{stroke:rgb(107, 198, 127);fill:rgb(243, 243, 243);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_cg_ text.actor>tspan{fill:rgb(13, 13, 13);stroke:none;}#chatgpt-mermaid-_r_cg_ .actor-line{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_cg_ .innerArc{stroke-width:1.5;stroke-dasharray:none;}#chatgpt-mermaid-_r_cg_ .messageLine0{stroke-width:1.5;stroke-dasharray:none;stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_cg_ .messageLine1{stroke-width:1.5;stroke-dasharray:2,2;stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_cg_ [id$="-arrowhead"] path{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_cg_ .sequenceNumber{fill:#707070;}#chatgpt-mermaid-_r_cg_ [id$="-sequencenumber"]{fill:rgb(143, 143, 143);}#chatgpt-mermaid-_r_cg_ [id$="-crosshead"] path{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_cg_ .messageText{fill:rgb(13, 13, 13);stroke:none;}#chatgpt-mermaid-_r_cg_ .labelBox{stroke:rgba(0, 0, 0, 0.1);fill:rgb(252, 252, 252);filter:none;}#chatgpt-mermaid-_r_cg_ .labelText,#chatgpt-mermaid-_r_cg_ .labelText>tspan{fill:rgb(13, 13, 13);stroke:none;}#chatgpt-mermaid-_r_cg_ .loopText,#chatgpt-mermaid-_r_cg_ .loopText>tspan{fill:rgb(13, 13, 13);stroke:none;}#chatgpt-mermaid-_r_cg_ .sectionTitle,#chatgpt-mermaid-_r_cg_ .sectionTitle>tspan{fill:rgb(13, 13, 13);stroke:none;}#chatgpt-mermaid-_r_cg_ .loopLine{stroke-width:2px;stroke-dasharray:2,2;stroke:rgba(0, 0, 0, 0.1);fill:rgba(0, 0, 0, 0.1);}#chatgpt-mermaid-_r_cg_ .note{stroke:rgb(107, 198, 127);fill:rgb(243, 243, 243);}#chatgpt-mermaid-_r_cg_ .noteText,#chatgpt-mermaid-_r_cg_ .noteText>tspan{fill:rgb(13, 13, 13);stroke:none;font-weight:normal;}#chatgpt-mermaid-_r_cg_ .activation0{fill:rgb(243, 243, 243);stroke:hsl(0, 0%, 85.2941176471%);}#chatgpt-mermaid-_r_cg_ .activation1{fill:rgb(243, 243, 243);stroke:hsl(0, 0%, 85.2941176471%);}#chatgpt-mermaid-_r_cg_ .activation2{fill:rgb(243, 243, 243);stroke:hsl(0, 0%, 85.2941176471%);}#chatgpt-mermaid-_r_cg_ .actorPopupMenu{position:absolute;}#chatgpt-mermaid-_r_cg_ .actorPopupMenuPanel{position:absolute;fill:rgb(222, 234, 251);box-shadow:0px 8px 16px 0px rgba(0,0,0,0.2);filter:drop-shadow(3px 5px 2px rgb(0 0 0 / 0.4));}#chatgpt-mermaid-_r_cg_ .actor-man circle,#chatgpt-mermaid-_r_cg_ line{fill:rgb(222, 234, 251);stroke-width:2px;}#chatgpt-mermaid-_r_cg_ g rect.rect{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_cg_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_cg_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_cg_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_cg_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_cg_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_cg_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_cg_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_cg_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_cg_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_cg_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_cg_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_cg_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_cg_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_cg_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_cg_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_cg_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_cg_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_cg_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}Do not accept the shot until required gate passesalt[Inspection fails][Inspection passes]par[Narration][Scene images]OperatorApproverCreate episode + upload brief/sources1Create episode2Store source PDFs + manifest3Create episode row, rev 14Start Standard execution5Draft script using source objects6Write script + scene/source mapping7Normalize and validate8Publish validated revision9CP1 callback: script ready10Review and approve11Approve exact revision/hash12SendTaskSuccess (callback)13TTS takes × sentences14Takes, transcripts, scoring metrics15Generate shots/attempts16Immutable image attempts17Inspect every attempt: full image, crops, cast ref18Verdict bound to image SHA-119Diagnose failure + suggest prompt revision20Revised prompt / rationale21Retry failed shot only22New attempt + immutable output23Inspect new attempt24Merge results + validate status gates25Conditional revision update26Render 540p draft27Draft video28CP2 callback: draft ready29Watch draft + add scene notes30Reject with scene notes31Save decision and notes32SendTaskFailure / rejection result33Rerender changed scenes/composition34New draft revision35CP2 callback again36Approve draft37Approve exact draft hash38SendTaskSuccess39Render final 1080p40Final MP441FFmpeg/Pillow technical checks42Review contact sheets43Review findings44CP3 callback: final + package45Approve final package46Approve final hash/package revision47SendTaskSuccess48Store upload-ready package49Mark ready for upload50OperatorApprover





Failure handling rules:
- GPU crash or Spot interruption: Batch job retries from its immutable input manifest. A completed attempt remains saved; retry gets a new attempt ID. Do not overwrite the previous output.
- Image inspection failure: retain the failed PNG and its SHA-1-bound verdict. Generate a revised positive-only prompt, new deterministic seed or adjusted seed according to the recorded retry policy, then re-run only that shot. Do not mark visuals ready until every required attempt has a passing verdict or a human override.
- Claude inspection error/timeout: this is not a pass. Retry the inspection call or put the shot into a human-review state; no automatic “best effort” acceptance.
- Worker result arrives late: the merger checks its item ID, expected revision, current job state and source hash. A result from an older revision cannot silently replace the current selected item.
- Draft rejected: attach notes to the draft hash and affected scene IDs; invalidate only downstream artefacts that depend on changed inputs. Store the rejected draft and decision for audit.
- Approval page opened on stale revision: disable the approval action and require the page to reload the current revision. This prevents an approver approving a different video than the one shown.
- Repeated failure: route to operator attention after a configured retry budget; retain the exact stderr/logs and failed inputs for diagnosis.
Step Functions callback tokens are the bridge from the human approval API back into the paused workflow. Keep their storage encrypted and their use restricted to the approval Lambda. The callback API should be idempotent: duplicate taps must not produce multiple stage advances. 

AWS Step Functions+1

G. Porting the Mac-only parts
The objective is not to reproduce Apple Silicon in the cloud. It is to preserve the stage contracts and quality checks while replacing MLX implementations with CUDA-capable workers.
Model/runtime migration matrix
Current stage/model	Cloud equivalent	What is verified	What must be retested
Maya 2 Native TTS	maya3 Python package, CUDA 12.8 on Linux/NVIDIA	The current Maya 2 Native release documents CUDA inference, Hindi support, 20 built-in voices and 24 kHz audio	Voice selection, Hindi pronunciation, pacing, prosody, seed/repeatability and take-scoring behaviour
Veena TTS	Transformers + PyTorch + SNAC + bitsandbytes	Its model card documents a 3B Llama-based Hindi/English TTS model, 24 kHz SNAC output and Apache-2.0 licence declaration	CUDA quantisation, memory, long-sentence stability, Hindi pronunciation, voice drift and output quality
Whisper large-v3-turbo	faster-whisper/CTranslate2 on CUDA	CUDA 12 + cuDNN 9 are supported requirements; word-level timestamps are exposed by word_timestamps=True	Hindi CER, punctuation, code-mixed speech, word boundary accuracy and silence snapping
FLUX.2 Klein 4B	BFL's official FLUX.2 inference repo on an AWS Batch GPU worker; ComfyUI only after node/version pinning	Official repository lists text-to-image plus single- and multi-reference editing; 4B is Apache-2.0	Character identity, crop-stage accuracy, hand/action physics, reference adherence, quantisation and seed reproducibility
Image inspection	Claude vision through Bedrock	Claude Sonnet 5 on Bedrock supports image input and has an India geo-inference profile	Inspection consistency across full images/crops, false accepts, false rejects and agreement with human review

Important Maya model identity discrepancy
The supplied description calls Maya 2 Native a Llama-style LM with SNAC. The current public Maya 2 Native release 1.0 describes a different configuration: Qwen3-1.7B backbone, Kyutai Mimi codec and SpeechBrain speaker encoder. Its repository is named maya2-native, but its Python package/class are maya3 / Maya3TTS. It supports Hindi, has 20 built-in voices and runs on Linux with CUDA 12.8 and at least 8 GB GPU memory. The model card states approximately 5 GB of BF16 weights; its documented engine is not an MLX runtime. 

GitHub+2

That mismatch may reflect an older checkpoint or an internal fork in the current Mac pipeline. Before porting, record the exact model ID, revision hash, tokenizer, codec, voice roster and loader used by the Mac. Do not silently replace the existing voice with a differently trained release simply because the model name looks the same.
Recommended CUDA workers
TTS worker
- Build a version-pinned Linux container using Python 3.10–3.12 and CUDA 12.8 for the current Maya 2 Native reference engine.
- Use g6.2xlarge for the first benchmark. The documented Maya engine's 8 GB minimum makes an L4 worker a comfortable starting point for a single inference process.
- Use built-in named synthetic voices only. Although Maya 2 Native documents zero-shot cloning, AgriGate's policy should disable that path and reject any human-supplied voice reference.
- Run each take as a separate idempotent job. Record model/revision, voice, seed, text hash, settings, duration and output hash alongside the WAV.
Veena worker
- Use the documented Transformers/PyTorch/SNAC path with bitsandbytes 4-bit NF4 as the first CUDA test.
- Keep a separate container and model cache from Maya. Do not install both stacks into one unpinned Python environment.
- Pin the exact Hugging Face commit. The model card's displayed repository tag and its explicit licence metadata should be checked against the pinned files before production use; see section H.
Whisper worker
- Use faster-whisper with the same large-v3-turbo checkpoint. Its current CUDA installation documentation calls for cuBLAS for CUDA 12 and cuDNN 9. The API supports word timestamps. 
  
  GitHub+1
- Keep the custom Hindi letter/script alignment and silence snapping. Do not assume a generic forced aligner will improve this pipeline; validate it against the existing alignment first.
- Keep model and decoder version fixed across the N-take scoring loop. Otherwise the candidate takes may be scored by subtly different ASR versions.
Image generation worker
- Start from Black Forest Labs' official FLUX.2 repository rather than an unpinned third-party ComfyUI workflow. The official repo identifies FLUX.2 Klein 4B as a consumer-GPU-capable model and explicitly lists single- and multi-reference editing support under Apache-2.0. FLUX.2 Klein 9B and FLUX.2 Dev are listed under a non-commercial licence, so do not use those weights for AgriGate. 
  
  GitHub+1
- Build a single image-worker interface that accepts prompt, reference_images, seed, width, height, attempt_id and model_revision. The worker should return an image plus a JSON sidecar. That preserves the current subprocess JSON contract.
- Store every generated attempt immediately; do not overwrite a previous file when retrying.
- ComfyUI is acceptable as a pinned execution graph if its exact nodes support the required edit mode and multi-reference input. Diffusers is a possible implementation route, but do not assume an adapter supports the exact Klein edit mode until the image A/B test proves it. For a faithful initial port, the BFL reference implementation is the safer baseline.
Quality parity test plan
Run the same fixed benchmark corpus through the Mac and cloud implementations before switching production traffic:
Test	Minimum benchmark	Acceptance measure
Hindi TTS	100–200 sentences covering numbers, units, currency, fractions, place/crop names, code-mixing and all delivery styles	Blind human preference, pronunciation error, intelligibility, naturalness, pause quality and no material degradation against Mac
N-take selection	30 sentences × 5–6 takes on both backends	Same scoring metrics; measure whether the automatic winner is still preferred by human listeners
ASR and timing	50 final audio clips with manually corrected word boundaries	Hindi CER and word-timing error; target a pre-agreed timing tolerance such as median absolute error below 100 ms
Character consistency	At least 30 reference-edit shots covering several scenes and camera distances	Blind human identity match; inspect at original size and 2× crops
Farming/action accuracy	At least 30 images with soil, seeds, tools, fertiliser containers and crop-specific scenes	No new critical errors in hands, tool grip, material flow, crop stage or action physics
Determinism	Repeat the same image job with identical inputs and seed	Record whether exact pixels, perceptual similarity or only semantic consistency is reproducible
Audio delivery	Final assembled narration	Keep existing pause rules, -14 LUFS target and no clipping

For images, compare not only the selected outputs but all failed and accepted attempts. A CUDA port that generates a good final pick but changes inspection failure rates is not necessarily a safe migration.
Which image models become worth testing?
More GPU memory does not remove licence restrictions. The useful shortlist is:
- FLUX.2 Klein 4B self-hosted: first production baseline. Its official licence and reference-edit support make it the most straightforward commercial open-weight choice in this comparison.
- FLUX.3 Image Klein: your reported bake-off leader is worth licensing and benchmarking. Black Forest Labs currently says running Klein in a commercial product requires a commercial licence for self-hosted deployment at scale. Get the terms in writing, including whether your proposed quantised checkpoint is covered, before loading it into production. 
  
  Black Forest Labs+1
- FLUX.2 Pro / Max API: useful paid quality comparators if you are willing to send reference images to an external provider. BFL lists reference-image input and per-megapixel pricing; this avoids running a larger GPU worker yourself. It does not provide the same self-hosted control over model weights and local execution. 
  
  Black Forest Labs+1
I would not promote FLUX.2 Klein 9B or FLUX.2 Dev as production candidates under the stated commercial licensing constraint unless BFL supplies a different written commercial grant. A larger GPU is not a licence.
H. Security, licences and operations
Identity and least privilege
Use Cognito User Pools for control-room login, MFA for approvers and two application groups (operator, approver). Keep approval permissions separate from normal application administration. A user may hold both roles only if AgriGate deliberately chooses that policy, but the agent and all worker roles must never receive the approver role.

Use separate IAM task roles:
- Workflow role: start and monitor Batch jobs, invoke approved Lambda tasks, read episode pointers and call only the necessary callback APIs.
- Source-fetch role: fetch only allow-listed government/ICAR domains and write to the source prefix. It cannot edit scripts or approve.
- Claude/Agent role: read only the episode inputs it needs, write to a draft/agent workspace and invoke an allow-listed set of tools. It cannot update approval records, call callback APIs or write the canonical episode pointer.
- TTS/ASR role: read selected text/audio inputs and write to the matching audio result prefixes.
- Image role: read prompts and cast references; write new attempt objects and result sidecars. It cannot overwrite approved selections.
- Render/QA role: read immutable approved inputs, write render and QA outputs.
- Approval API role: read current revision/hash, write approval records and invoke Step Functions callback success/failure. This is the only component with callback permission.
Explicitly deny agent/worker roles access to the approval DynamoDB keys and SendTaskSuccess/SendTaskFailure. An IAM permissions boundary or SCP can provide a further guard against accidentally broadening these roles.
Secrets and network
- Prefer Bedrock IAM authentication rather than a stored Anthropic API key. If a third-party API is used, keep the key in Secrets Manager, expose it only to that task and rotate it.
- Store YouTube OAuth refresh tokens in Secrets Manager encrypted with KMS. Use the upload role only after checkpoint 3.
- Keep Batch GPU hosts in private subnets. Use VPC endpoints for S3, ECR, CloudWatch Logs, Secrets Manager and other supported AWS services. Stage model files in S3 during a controlled build/deployment step so GPU jobs do not need unrestricted internet egress on every launch.
- Encrypt S3, DynamoDB backups and logs with KMS; use TLS between browser, API, workers and storage.
- Use CloudFront signed URLs for review media; never give the browser a broad S3 credential.
Licensing assessment
Component	Current licence position	Production decision
Maya 2 Native 1.0	Model card states Apache-2.0 weights and inference code; upstream Mimi component is CC-BY-4.0	Suitable with attribution and a component inventory
Veena	Model card declares Apache 2.0, but also displays a proprietary tag in its metadata	Hold for legal review of pinned files and confirmation from publisher
Whisper	Official Whisper repo says MIT for code and model weights	Suitable; keep the MIT notices
faster-whisper	Separate runtime project; pin and retain its own licence notices	Confirm the exact package/revision in the SBOM
FLUX.2 Klein 4B	Apache-2.0	Suitable; preserve notices
FLUX.2 9B / Dev	Non-commercial licence in official FLUX.2 table	Do not use for revenue-producing videos
FLUX.3 Image Klein	Commercial self-hosted use requires a commercial licence per BFL	Do not deploy until signed
Claude via Bedrock	Paid API usage under AWS/Anthropic model terms	Suitable subject to Bedrock terms and data-handling review
Remotion	Free licence covers individuals and organisations/teams of up to 3 people, including automation; company licences have a separate Automators plan	Verify AgriGate's total eligible headcount and terms before budgeting

The current Remotion FAQ explicitly says eligible companies with up to three people can use the free licence and run automation. For organisations that do not qualify for the free licence, the Automators option is $0.01 per render with a $100/month minimum. So do not budget the $100 automatically—but also do not assume the two-person production team is the whole company headcount. 

Remotion+2

Synthetic voice and face policy: use only named, model-provided synthetic voices or synthetic references created for AgriGate. Disable zero-shot voice cloning, reject real-person audio references and do not create or use real-person faces. Keep the generated character reference asset and all derivative shot hashes in the audit record.
Observability and operations
Use structured JSON logs with episode_id, stage, job_id, item_id, attempt, model_revision, input_hash, output_hash, duration_ms and outcome. Send logs to CloudWatch and save the stage summary to the episode's append-only S3 event log.

Every worker should emit a cost record containing:
- billed GPU/CPU seconds and instance type;
- API model name, input/output tokens and provider-reported usage;
- image count, resolution, reference image count and attempts;
- render duration, Lambda configuration and output size;
- artefact/storage size and transfer bytes where available.
Tag all AWS resources with app=agrigate, episode_id where possible, environment and stage. Use AWS Budgets, Cost Anomaly Detection and quota alarms. Keep a per-episode ledger in DynamoDB for the dashboard, but reconcile it against actual Cost and Usage Reports because estimated runtime cost is not a billing record.
Dashboard and notification implementation
Host the static React control room on S3 + CloudFront (or Amplify Hosting) with Cognito authentication. Use API Gateway HTTP APIs for commands and a WebSocket API for progress. A small EventBridge/DynamoDB Streams consumer can publish job updates; the UI should poll as a fallback.

Start with SES email notifications. Add Slack via a webhook adapter if your team already uses it. Add WhatsApp only after deciding the provider, message-template/consent process and regional data-handling requirements; I have not included a WhatsApp per-message price in the estimate because that depends on the chosen provider and message category.

For YouTube, use the official Data API's videos.insert after checkpoint 3, save the returned video ID and upload status, and default to private until the package is explicitly scheduled. The current Data API documentation gives videos.insert a 256 GB maximum media-file size and lists a default 100 uploads/day quota, which is ample for 60/month. 

developers.google.com+1

Deployment and maintenance
Use AWS CDK or Terraform; I would choose CDK in TypeScript if the team already maintains TypeScript for Remotion. Keep the following as separate deployable units:
- control-plane: Cognito, S3/CloudFront, API Gateway, Lambda, DynamoDB.
- workflow: Step Functions, EventBridge rules, queues and approval callbacks.
- workers: Batch job definitions, GPU compute environments, ECR images and model manifests.
- rendering: Remotion Lambda deployment and the rendering bundle.
- monitoring: CloudWatch dashboards, alarms, Budgets and notification rules.
CI/CD should build worker images, scan dependencies, generate an SBOM, publish to ECR and deploy through an AWS role assumed using GitHub Actions OIDC. Pin model revisions, container digests, Python dependencies, CUDA base images, Remotion version and font files. A production episode should record those versions in its manifest so a future rerender can reconstruct the environment.
I. Cost model
These are planning estimates in USD, not a formal AWS quote. They exclude labour, tax, support plans, YouTube advertising and any paid licence not listed below.
Assumptions behind the model
- One long episode contains around 40 image shots and averages 1.5 attempts per shot: approximately 60 generated/inspected image attempts.
- Audio uses 5–6 takes per narration sentence, followed by ASR scoring and word timing.
- The image worker uses g6e.2xlarge for approximately 0.5–1.0 billed GPU hours per episode. At the Mumbai on-demand estimate of about $2.69/hour, that is about $1.35–$2.69 per episode.
- Audio and ASR use g6.2xlarge for approximately 0.5–1.0 billed GPU hours. A Mumbai on-demand estimate around $1.17/hour gives roughly $0.60–$1.20. Spot may reduce this, but capacity and interruption risk make it unsuitable as the only assumption.
- Claude costs include script drafting, inspection of each image attempt at full size plus crops/reference, prompt revision and contact-sheet review.
- Rendering includes a final and several draft/re-render passes.
- GPU prices above come from third-party regional price trackers, not a guaranteed AWS quote. Validate actual AZ capacity, On-Demand price and Spot price in the AWS Pricing Calculator/account before enabling production. 
  
  EC2 Prices+3
Estimated variable cost per long episode
Cost item	Assumption	Estimated cost
TTS + Whisper	g6.2xlarge, 0.5–1.0 GPU hours	$0.60–$1.20
Image generation	g6e.2xlarge, 0.5–1.0 GPU hours	$1.35–$2.70
Claude script + visual inspection + QA	Sonnet 5 on India Bedrock profile	$2.00–$5.00
Remotion rendering	Drafts, rerenders and final	$0.20–$0.90
CPU stages, storage, queueing and transfers	Lambda/Fargate, S3, API and orchestration allocation	$0.15–$0.55
Total		$4.30–$10.35

I would budget $4–$11 per long episode until measured cloud timings replace these assumptions.

For Claude, the current Anthropic price sheet dated 9 November 2026 lists Sonnet 5 on Bedrock at $2.20 per million input tokens and $11 per million output tokens for in-region/geo-cross-region inference. A budget of $2–$5 per episode assumes roughly 0.5–1.5 million input tokens across visual inspection, script and review, plus generated text and retries. Actual vision token use depends on crop size and prompt format. 

2026-11-09+1

Fixed monthly platform cost
Platform item	Planning range/month
S3 storage, versions and lifecycle overhead	$3–$12
CloudFront preview delivery	$3–$15
API Gateway, Lambda, EventBridge, SQS and Step Functions	$5–$15
DynamoDB, backups and KMS	$3–$10
CloudWatch logs, alarms and monitoring	$8–$20
VPC endpoints, secrets, email and miscellaneous services	$13–$28
Estimated fixed platform total	$35–$100

This assumes there is no always-on GPU or application server, model weights are stored in S3, the control room is static-hosted, and network egress is controlled. A NAT Gateway, high-volume logging, frequent large-video downloads or extended CloudFront egress can increase this.

Step Functions Standard currently has 4,000 free state transitions/month. Above that, its per-transition charge is small relative to GPU and Claude usage; even at 1,000 transitions per episode, the orchestration charge should not dominate at 60 episodes/month. 

aws.amazon.com+1

Monthly totals
Volume	Variable cost	Fixed platform	Estimated monthly total
12 long episodes	$52–$124	$35–$100	$87–$224
60 long episodes	$258–$621	$35–$100	$293–$721

A reasonable midpoint budget is approximately $140/month at 12 episodes and $500/month at 60 episodes, before Shorts and any additional licence.

Possible Remotion licence addition: $0 if AgriGate qualifies for its free licence; otherwise budget at least $100/month for the Automators option. The current terms price this at $0.01 per render with a $100/month minimum. The free licence covers eligible organisations or teams of up to three people, including automation, so check the company-wide headcount and exclusions rather than the size of the production team alone. 

Remotion+1

Alternative image-generation economics
A BFL API route is worth testing. Its published FLUX.2 Klein 4B pricing is $0.014 for the first output megapixel, $0.001 per additional megapixel and $0.001 per reference-image megapixel. At 60 one-megapixel outputs with one one-megapixel reference per image, that is about $0.90 before any additional resolution or retry usage. 

Black Forest Labs+1

That can be cheaper than the estimated AWS GPU-hour cost. I would nevertheless retain AWS Batch as the initial default because it keeps model execution and reference images within your AWS environment. Run a blind comparison between local FLUX.2 Klein 4B and the BFL API for likeness consistency, edit adherence, determinism, latency and licence/data terms. Promote the API if its quality is at least as good and its data-handling terms meet your requirements.

What dominates? At the current volume, Claude visual inspection and the image GPU are likely to be the two largest lines. If you switch image generation to the BFL API, Claude inspection becomes the likely dominant per-episode cost. Remotion and Step Functions should remain comparatively small.

Shorts are not included in the totals. Estimate them separately by measuring how many new image attempts, narration seconds and render passes they require; a Short made mostly by recutting existing long-video assets should cost much less than a new long episode.
J. Phased migration plan
Each phase is usable on its own. During migration, the Mac can remain a temporary fallback for the MLX model stages, but it should never remain a production dependency after the final phase.
Phase	Deliverable	What can still run on the Mac	Acceptance test
0. Contract and containers	Freeze Pydantic schema, TypeScript types, model manifests and JSON worker contracts; create CDK/Terraform and ECR repositories	Development and local tests only	Round-trip an existing episode through the cloud schema validator without changing meaning or losing metadata
1. Cloud storage and control room	S3 object layout, DynamoDB episode index, Cognito login, mobile review UI, source upload and preview playback	The local pipeline may still generate assets for upload	Upload a complete existing episode to S3; review its video/audio from a phone; prove no bucket is public
2. Workflow and script stage	Step Functions Standard, source fetcher, Claude Bedrock script generation, normalization, validators and CP1 callback	Mac may continue generating narration and images	Run a script-only episode to CP1; verify missing source, absent source reference and [VERIFY] block approval
3. Audio migration	CUDA containers for Maya and Veena; faster-whisper; Batch queue and result merger	Mac remains fallback TTS/ASR for parity testing	A/B 100–200 identical Hindi sentences; compare human preference, CER, pauses, voice identity and word timings
4. Image migration	FLUX.2 Klein 4B CUDA worker, reference-edit mode, attempt history, inspection crops, Claude vision gate	Mac remains fallback image generator for comparison	Blind review at least 30 shots; every attempt must have a SHA-1-bound inspection result, and failed attempts must not pass the visual gate
5. Cloud rendering and QA	Remotion Lambda deployment, bundled Devanagari fonts, FFmpeg/Pillow QA and final output	Mac can be used only as a reference renderer during comparison	Render a full long episode in AWS; compare captions, timing, composition, audio loudness, black frames, freezes and font rendering
6. Approval enforcement	Three callback checkpoints, approver roles, audit history, notification and stale-revision protection	Mac is not required for approvals or job control	Try to approve from the agent role and every worker role; all must fail. Simulate CP1, CP2 and CP3 rejection and approval from a phone
7. Fully cloud production	Remove local execution and filesystem assumptions; add private YouTube upload after CP3	Mac is used only for development and optional monitoring	Disconnect or shut down the Mac and run an entire episode from brief to approved package, with a failed image retry and at least one rejected draft

Migration safeguards
Do not cut over an entire category at once. At the beginning of phases 3–5, keep the Mac implementation as a comparison backend behind the existing configuration switch. Use the same inputs and save the two outputs under different backend IDs.

Keep the cloud stage contract stable. For example, the TTS stage should still expose:
synthesize(    text: str,    voice_cfg: dict,    seed: int,    out_path: str,) -> float



The selected backend changes through configuration; the orchestrator should not need to know whether the implementation uses MLX, CUDA or an API.

After a stage passes parity tests, route production traffic to the cloud backend by default. Retain the old Mac code and its model manifests until at least a full production cycle has been completed and the rollback procedure has been tested.
K. Risks and open questions
Risk / unresolved question	Why it matters	Action before production
Which exact Maya checkpoint runs today?	The latest public Maya 2 Native release does not match the supplied Llama/SNAC description	Record model ID, commit, codec and environment from the Mac; make a pinned cloud-versus-Mac benchmark
Veena artefact licence clarity	The model card declares Apache-2.0, while its metadata includes a proprietary tag	Obtain written confirmation for the exact weights, code and upstream dependencies used
FLUX.3 Klein commercial terms	Current BFL guidance requires a commercial licence for self-hosting in a product	Get a signed licence and verify quantised weights are covered before production
Actual AWS GPU-hour availability in Mumbai	G6/G6e family support does not guarantee a particular AZ has capacity when needed	Check capacity in target AZs, request quotas, and benchmark On-Demand plus Spot fallback
Cloud image inspection false accepts	The existing pipeline has a strict safety/quality gate that a vision model can still miss	Run a human-labelled challenge set of failure images, measure false accepts and keep ambiguous cases human-routed
Image determinism across hardware	Seeds may not produce byte-identical results across kernels, frameworks and precision modes	Log all generation parameters, retain every attempt and define whether repeatability means exact pixels or perceptual similarity
Claude model lifecycle and regional availability	A model name or regional profile may change during the product lifecycle	Pin model IDs, test fallback models and monitor Bedrock quotas and deprecation notices
Human approval authority	If a worker or agent can update status, checkpoints become conventions rather than controls	Run IAM negative tests as part of CI/CD; keep approval callbacks in a separate role
Source quality and conflicting agronomy advice	A model can produce fluent but unsupported farming guidance	Require source-backed scenes, persist source URLs/files and conflicts, and preserve [VERIFY] rejection
Long-running renders and asset transfer	A Lambda render can be constrained by its 15-minute timeout and scratch-space budget	Benchmark a full 1080p long episode, including stitching and upload; fall back to container rendering if it breaches the limit
YouTube API changes and OAuth	Uploading as private/scheduled requires correct channel authorisation and quota handling	Begin with a private test channel, use resumable uploads, and verify scheduling behavior before automating public release
Storage retention cost	Keeping every attempt and take is intentional but accumulates	Review S3 storage by class quarterly; transition old attempt artefacts only after testing retrieval and audit needs

Alternatives rejected
A rented cloud Mac running the current pipeline unchanged. This is attractive for the first week because MLX works without code changes. It does not solve the target architecture: it leaves the pipeline tied to Apple-specific runtimes and one machine shape, and it retains serial workload execution. It is an acceptable short-lived parity or migration fallback, not the production design.

One always-on GPU VM. It creates idle GPU spend between infrequent episodes and adds a server to patch, monitor and recover. At the indicative Mumbai g6e.2xlarge estimate of around $2.69/hour, an always-on month would cost around $1,960 before storage and other charges. Batch is a better fit.

Kubernetes/EKS. It is technically capable but brings cluster, node, networking and deployment operations that do not justify themselves for a 1–2 person production team and this workload. Revisit it only if there is a real multi-team platform or a need for persistent GPU serving.

Temporal, Prefect or Dagster as the main orchestrator. These can orchestrate durable work, but introduce an additional platform and operational responsibility. Step Functions already has the AWS Batch integrations and long-lived callback pattern needed here. Temporal may be worth revisiting if the workflow grows into many cross-cloud services or needs more sophisticated workflow portability.

LangGraph as the episode workflow engine. It is useful for agent reasoning and tool loops, but should not be the system of record for job execution and approval permissions. Keep Claude's multi-step reasoning inside a stage; let Step Functions own workflow state, retries and checkpoint waits.

Fully managed video or image APIs for the whole pipeline. They could shorten implementation time, but may hide important controls over model revisions, per-shot attempts, seed behavior, reference editing and audit. Use model APIs selectively where benchmarked quality and price are compelling; keep the episode contract and gate logic in AgriGate.

Remotion replaced with MediaConvert. MediaConvert is useful for media transcoding and packaging, but it is not a drop-in replacement for a React composition with Hindi text, word highlighting, animated graphics and scene-specific layouts. Remotion remains the better match for the current pipeline.
L. Sources consulted
Research baseline: 22 November 2026. For live service and pricing pages without an explicit publication date, the date below is the date checked. Pricing and service availability can vary by region, account, quota and selected service tier.
Topic	Documentation / pricing source	Date and confidence
Workflow execution and human callbacks	Step Functions workflow types, callback task pattern	Checked 22 Nov 2026. High for documented capabilities; quotas should be rechecked in the account.  AWS Step Functions+2
AWS Batch GPU workers and pricing	AWS Batch pricing, AWS Batch FAQs	Checked 22 Nov 2026. High for no separate Batch charge and GPU scheduling; instance availability/pricing varies.  aws.amazon.com+1
GPU families in Mumbai	AWS EC2 GPU instance specifications, AWS regional product list	Checked 22 Nov 2026. High for family capability and listed regional availability; lower confidence for exact hour costs.  Amazon EC2+2
EC2 GPU price assumptions	Third-party Mumbai EC2 price tracker	Checked 22 Nov 2026. Medium-low for indicative hourly estimates; use the AWS Pricing Calculator for the actual account/AZ.  DoiT Compute+1
Claude model/data locality	AWS Bedrock Sonnet 5 model card, AWS announcement of India availability	Announcement 29 Sep 2026; documentation checked 22 Nov. High for Sonnet 5 India geo profile and model support.  AWS+2
Claude pricing	Anthropic list prices, 9 Nov 2026	Published 9 Nov 2026. High for listed token rates; actual visual token counts are workload-dependent.  2026-11-09+1
Maya 2 Native	Maya 2 Native model card, inference engine repository	Release 1.0 dated 25 Oct 2026; checked 22 Nov. High for documented CUDA engine, model card, voice roster and licences; parity still requires testing.  Hugging Face+2
Veena TTS	Veena model card	Checked 22 Nov 2026. Medium for declared model architecture and Apache-2.0 metadata; obtain licence confirmation for exact artefacts.  Hugging Face+1
Whisper/faster-whisper	OpenAI Whisper, SYSTRAN faster-whisper	Checked 22 Nov 2026. High for MIT statement, CUDA dependencies and word timestamp API.  GitHub+2
FLUX.2 open weights and edit support	BFL FLUX.2 repository	Checked 22 Nov 2026. High for official model/feature/licence table.  GitHub+1
FLUX.3 Klein commercial terms	BFL FLUX.3 Image Klein product page	Checked 22 Nov 2026. High for BFL's current commercial-licence statement.  Black Forest Labs
BFL API image pricing	BFL pricing	Checked 22 Nov 2026. High for per-megapixel list rates; output size and references drive final price.  Black Forest Labs+1
Remotion Lambda	Remotion Lambda documentation	Checked 22 Nov 2026. High for regional support, parallel rendering pattern and stated timeout constraint.  Remotion+1
Remotion licence	Remotion licence FAQ, terms and conditions	Checked 22 Nov 2026. High for current published eligibility and pricing; company headcount and legal eligibility still need confirmation.  Remotion+1
State, storage concurrency and approvals	DynamoDB conditional writes, S3 conditional writes	Checked 22 Nov 2026. High for conditional-write/optimistic concurrency primitives.  Amazon DynamoDB+3
YouTube upload	YouTube Data API videos.insert	Checked 22 Nov 2026. High for upload method, media limit and quota statement; quotas remain subject to the channel/API project.  developers.google.com+1

Bottom line
Build the first production version around Step Functions Standard + S3/DynamoDB + AWS Batch GPU workers + Claude on Bedrock + Remotion Lambda, with a deliberately small, role-separated control plane. Port Maya/Veena/Whisper and FLUX.2 Klein 4B behind the existing backend contracts. Keep the image inspection gate mandatory and make its verdict immutable. Most importantly, make approvals a workflow permission boundary—not a checkbox in Claude's prompt.

The two decisions I would resolve before committing production spend are the exact Maya checkpoint currently running on the Mac and whether AgriGate qualifies for Remotion's free licence. Everything else can be proven through the staged migration tests above.