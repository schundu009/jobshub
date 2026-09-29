/**
 * Skills taxonomy and matcher shared by the Jobs page.
 *
 * Every skill has a canonical name, a category and the aliases it appears as
 * in postings and resumes. extract() returns every skill found in a text (no
 * cap); compare() lists all of them on both sides: matched, missing from the
 * resume, and resume-only.
 */
(function () {
    const T = (cat, list) => list.map(entry => {
        const [name, ...aliases] = Array.isArray(entry) ? entry : [entry];
        return { name, cat, aliases: [name, ...aliases] };
    });

    const TAXONOMY = [
        ...T('Language', [
            'Python', 'Java', ['JavaScript', 'ecmascript', 'es6'], ['TypeScript'], ['Go', 'golang'],
            'Rust', ['C++', 'cpp'], ['C#', 'csharp'], 'C', 'Scala', 'Kotlin', 'Swift', ['Objective-C', 'objc'],
            'Ruby', 'PHP', 'Perl', ['Bash', 'shell scripting', 'shell script', 'bash scripting'], ['PowerShell'],
            ['SQL', 't-sql', 'tsql', 'pl/sql', 'plsql'], 'Elixir', 'Erlang', 'Haskell', 'Clojure',
            ['R', 'r programming', 'rstudio'], 'Julia', 'Lua', 'Dart', 'Groovy', ['MATLAB'], ['Solidity'], ['Zig'],
            ['Fortran'], ['COBOL'], ['Verilog'], ['VHDL'], ['WebAssembly', 'wasm'],
        ]),
        ...T('Frontend', [
            ['React', 'react.js', 'reactjs'], ['Next.js', 'nextjs'], ['Vue', 'vue.js', 'vuejs'], ['Nuxt', 'nuxt.js'],
            ['Angular', 'angularjs'], 'Svelte', ['Redux'], ['HTML', 'html5'], ['CSS', 'css3'], ['Sass', 'scss'],
            ['Tailwind', 'tailwindcss', 'tailwind css'], ['Webpack'], ['Vite'], ['Storybook'], ['jQuery'],
            ['React Native'], ['Flutter'], ['Electron'], ['D3.js', 'd3'], ['Three.js'], ['WebGL'], ['Accessibility', 'wcag', 'a11y'],
        ]),
        ...T('Backend', [
            ['Node.js', 'nodejs', 'node js'], ['Express', 'express.js'], ['NestJS'], ['Django'], ['Flask'], ['FastAPI'],
            ['Spring Boot', 'spring framework'], ['.NET', 'dotnet', 'asp.net', '.net core'], ['Rails', 'ruby on rails'],
            ['Laravel'], ['GraphQL'], ['gRPC'], ['REST', 'restful', 'rest api', 'rest apis'], ['Protobuf', 'protocol buffers'],
            ['Microservices', 'microservice', 'service-oriented architecture'], ['Event-driven architecture', 'event driven', 'event-driven'],
            ['Distributed systems', 'distributed system', 'distributed computing'], ['System design'], ['API design', 'api development'],
            ['WebSockets', 'websocket'], ['OAuth', 'oauth2', 'oidc', 'openid connect'], ['Celery'], ['Sidekiq'],
        ]),
        ...T('Cloud', [
            ['AWS', 'amazon web services'], ['GCP', 'google cloud', 'google cloud platform'], ['Azure', 'microsoft azure'],
            ['OCI', 'oracle cloud'], ['EC2'], ['S3'], ['AWS Lambda', 'lambda'], ['ECS'], ['EKS'], ['GKE'], ['AKS'], ['IAM'],
            ['CloudFormation'], ['CloudFront'], ['RDS'], ['Aurora'], ['SQS'], ['SNS'], ['Kinesis'], ['Route 53', 'route53'],
            ['VPC'], ['Cloud Run'], ['Cloud Functions'], ['BigQuery'], ['Pub/Sub', 'pubsub'], ['Serverless'], ['Multi-cloud', 'multicloud', 'hybrid cloud'],
            ['Cloudflare'], ['Heroku'], ['OpenStack'], ['VMware', 'vsphere', 'esxi'],
        ]),
        ...T('Containers & orchestration', [
            ['Kubernetes', 'k8s'], ['Docker', 'dockerfile', 'docker compose'], ['Helm'], ['OpenShift'], ['containerd'],
            ['Podman'], ['Istio'], ['Linkerd'], ['Envoy'], ['Service mesh'], ['Nomad'], ['Kustomize'], ['Kubernetes operators', 'k8s operators'],
            ['Karpenter'], ['Knative'], ['Containers', 'containerization', 'containerized'],
        ]),
        ...T('Infrastructure as code', [
            ['Terraform'], ['Pulumi'], ['Ansible'], ['Chef'], ['Puppet'], ['SaltStack'], ['Packer'], ['Crossplane'],
            ['AWS CDK', 'cdk'], ['Infrastructure as code', 'IaC'], ['Vagrant'],
        ]),
        ...T('CI/CD & tooling', [
            ['CI/CD', 'ci / cd', 'continuous integration', 'continuous delivery', 'continuous deployment'], ['Jenkins'],
            ['GitHub Actions'], ['GitLab CI', 'gitlab ci/cd'], ['CircleCI'], ['Travis CI'], ['Argo CD', 'argocd'],
            ['Argo Workflows'], ['FluxCD'], ['Spinnaker'], ['Tekton'], ['Bazel'], ['Gradle'], ['Maven'], ['Git'],
            ['GitOps'], ['Artifactory'], ['SonarQube'], ['Buildkite'], ['TeamCity'],
        ]),
        ...T('Observability & SRE', [
            ['Prometheus'], ['Grafana'], ['Datadog'], ['Splunk'], ['New Relic'], ['Dynatrace'], ['OpenTelemetry', 'otel'],
            ['Jaeger'], ['Zipkin'], ['ELK stack', 'elk'], ['Kibana'], ['Logstash'], ['Fluentd', 'fluent bit'], ['Loki'],
            ['PagerDuty'], ['Sentry'], ['Honeycomb'], ['Nagios'], ['Zabbix'], ['CloudWatch'], ['Thanos'], ['VictoriaMetrics'],
            ['Observability'], ['Monitoring'], ['Alerting'], ['Distributed tracing'], ['SLOs', 'slo', 'slos', 'sli', 'slis', 'service level objectives'],
            ['Incident management', 'incident response', 'on-call', 'on call', 'oncall'], ['Postmortems', 'postmortem', 'post-mortem'],
            ['Site reliability engineering', 'SRE', 'site reliability engineer', 'site reliability'], ['Capacity planning'], ['Chaos engineering'], ['Performance tuning', 'performance optimization'],
            ['Disaster recovery', 'business continuity'], ['High availability'], ['Load balancing', 'load balancer', 'load balancers'],
            ['Autoscaling', 'auto-scaling', 'auto scaling'],
        ]),
        ...T('Databases', [
            ['PostgreSQL', 'postgres'], ['MySQL'], ['MariaDB'], ['SQL Server', 'mssql', 'microsoft sql server'], ['Oracle Database', 'oracle db'],
            ['SQLite'], ['MongoDB', 'mongo'], ['Cassandra'], ['ScyllaDB'], ['Redis'], ['Memcached'], ['Elasticsearch', 'elastic search'],
            ['OpenSearch'], ['DynamoDB'], ['Couchbase'], ['CockroachDB'], ['Spanner'], ['Neo4j'], ['ClickHouse'], ['TimescaleDB'],
            ['InfluxDB'], ['Vitess'], ['HBase'], ['Firestore'], ['Supabase'], ['Pinecone'], ['Weaviate'], ['pgvector'],
            ['Vector databases', 'vector database', 'vector db'], ['NoSQL'], ['Data modeling', 'data modelling', 'database design', 'schema design'],
        ]),
        ...T('Data engineering', [
            ['Spark', 'apache spark', 'pyspark'], ['Kafka', 'apache kafka'], ['Flink'], ['Airflow', 'apache airflow'], ['dbt'],
            ['Snowflake'], ['Redshift'], ['Databricks'], ['Hadoop'], ['Hive'], ['Presto', 'trino'], ['Apache Beam'],
            ['Dataflow'], ['Delta Lake'], ['Iceberg', 'apache iceberg'], ['Parquet'], ['Pulsar'], ['RabbitMQ'], ['NATS'],
            ['ETL', 'ELT'], ['Data pipelines', 'data pipeline'], ['Data warehousing', 'data warehouse'], ['Data lake', 'lakehouse'],
            ['Stream processing', 'streaming data', 'real-time data'], ['Pandas'], ['NumPy'], ['Polars'], ['Dagster'], ['Prefect'],
            ['Fivetran'], ['Looker'], ['Tableau'], ['Power BI'],
        ]),
        ...T('ML & AI', [
            ['Machine learning', 'ML'], ['Deep learning'], ['PyTorch'], ['TensorFlow'], ['JAX'], ['Keras'], ['scikit-learn', 'sklearn'],
            ['XGBoost'], ['LightGBM'], ['Hugging Face', 'huggingface'], ['LLMs', 'llm', 'large language models', 'large language model'],
            ['Generative AI', 'genai', 'gen ai'], ['RAG', 'retrieval augmented generation', 'retrieval-augmented generation'],
            ['LangChain'], ['LlamaIndex'], ['Prompt engineering'], ['Fine-tuning', 'fine tuning', 'finetuning'],
            ['NLP', 'natural language processing'], ['Computer vision'], ['Reinforcement learning'], ['Recommender systems', 'recommendation systems'],
            ['MLOps'], ['LLMOps'], ['MLflow'], ['Kubeflow'], ['SageMaker'], ['Vertex AI'], ['Ray'], ['Triton Inference Server'],
            ['vLLM'], ['TensorRT'], ['ONNX'], ['CUDA'], ['GPUs', 'gpu'], ['NCCL'], ['Model serving', 'model inference'],
            ['Feature stores', 'feature store'], ['Statistics'], ['A/B testing', 'ab testing', 'experimentation'],
        ]),
        ...T('Systems & networking', [
            ['Linux'], ['Unix'], ['Windows Server'], ['Linux kernel'], ['eBPF'], ['systemd'], ['Networking', 'computer networking', 'network engineering'],
            ['TCP/IP'], ['DNS'], ['HTTP/2', 'http2'], ['BGP'], ['VPN'], ['CDN'], ['Nginx'], ['HAProxy'],
            ['Firewalls', 'firewall'], ['SDN'], ['RDMA'], ['InfiniBand'], ['Slurm'], ['HPC', 'high performance computing', 'high-performance computing'],
            ['Distributed storage', 'storage systems'], ['Ceph'], ['NFS'], ['ZFS'], ['Virtualization', 'KVM', 'hypervisor'], ['Embedded systems'],
            ['Concurrency', 'multithreading', 'multi-threading'], ['Operating systems'],
        ]),
        ...T('Security', [
            ['Cybersecurity', 'information security', 'infosec', 'security engineering'], ['Application security', 'appsec'], ['Cloud security'],
            ['DevSecOps'], ['Zero trust'], ['TLS', 'SSL', 'mTLS', 'PKI'], ['HashiCorp Vault'], ['Secrets management'],
            ['SIEM'], ['SOC 2', 'soc2'], ['ISO 27001'], ['PCI DSS'], ['HIPAA'], ['GDPR'], ['FedRAMP'], ['Threat modeling'],
            ['Penetration testing', 'pentesting', 'pen testing'], ['Vulnerability management'], ['OWASP'], ['Cryptography', 'encryption'],
            ['Identity and access management'], ['SSO', 'single sign-on', 'SAML'], ['Okta'],
        ]),
        ...T('Testing & quality', [
            ['Unit testing', 'unit tests'], ['Integration testing', 'integration tests'], ['Test automation', 'automated testing'],
            ['Jest'], ['Pytest'], ['JUnit'], ['Selenium'], ['Cypress'], ['Playwright'], ['TDD', 'test-driven development'],
            ['Load testing', 'performance testing'], ['JMeter'], ['Code review', 'code reviews'],
        ]),
        ...T('Practices', [
            ['Agile'], ['Scrum'], ['Kanban'], ['Jira'], ['Confluence'], ['DevOps'], ['Platform engineering'], ['Technical leadership', 'tech lead'],
            ['Mentoring', 'mentorship'], ['Software architecture', 'solution architecture', 'systems architecture'], ['Design patterns'],
            ['Object-oriented programming', 'OOP', 'object oriented', 'object-oriented'], ['Functional programming'], ['Data structures'], ['Algorithms'],
            ['Cost optimization', 'finops'], ['Release management'], ['Stakeholder management'], ['Figma'],
            ['iOS'], ['Android'], ['Blockchain', 'web3'],
        ]),
    ];

    const esc = s => s.replace(/[.*+?^${}()|[\]\\\/]/g, '\\$&');
    // All-caps or very short forms (SRE, ML, IaC, KVM…) only count as written;
    // everything else matches case-insensitively.
    const isCaseSensitive = alias => alias.length <= 3 || /^[A-Z][A-Za-z]*[A-Z]/.test(alias) && alias === alias.toUpperCase();
    const GO_NOT_FOLLOWED_BY = '(?:to|ahead|live|beyond|further|back|through|deep|above|after|for|with|on|out|from|get|where|into|forward|the|a|an|ahead|live)';

    function aliasRegex(skill, alias) {
        if (skill.name === 'Go' && alias === 'Go') {
            return new RegExp(`(?<![\\w.\\-])Go(?![\\w\\-'’])(?!\\s+${GO_NOT_FOLLOWED_BY}\\b)`);
        }
        // Single letters count only inside a list ("C, C++", "Python, R and SQL").
        if (skill.name === 'C' && alias === 'C') return /(?<=(?:^|[,(\/:]|\band|\bor)\s*)C(?![\w+#\-\/])(?=\s*(?:,|\/|\band\b|\bor\b|\)|\.(?!\w)|$))/m;
        if (skill.name === 'R' && alias === 'R') return /(?<=(?:[,(\/:]|\band|\bor)\s*)R(?![\w\-\/&'’])(?=\s*(?:,|\/|\band\b|\bor\b|\)|\.(?!\w)|$))/m;
        if (skill.name === 'REST' && alias === 'REST') return /(?<![\w])REST(?![\w])/;
        const cs = isCaseSensitive(alias);
        const body = esc(alias).replace(/ /g, '[\\s\\-]+');
        return new RegExp(`(?<![A-Za-z0-9+#])${body}(?![A-Za-z0-9+#]|\\.[A-Za-z0-9])`, cs ? '' : 'i');
    }

    const MATCHERS = TAXONOMY.map(skill => ({ skill, rx: skill.aliases.map(alias => aliasRegex(skill, alias)) }));
    const BY_KEY = new Map();
    TAXONOMY.forEach(skill => skill.aliases.forEach(a => { if (!BY_KEY.has(a.toLowerCase())) BY_KEY.set(a.toLowerCase(), skill); }));

    function toText(value) {
        const s = String(value ?? '');
        if (!/<[a-z][\s\S]*>/i.test(s)) return s;
        const doc = new DOMParser().parseFromString(s, 'text/html');
        doc.querySelectorAll('br,p,li,div,h1,h2,h3,h4,tr').forEach(el => el.append('\n'));
        return doc.body.textContent || '';
    }

    /** Every skill found in the text, as [{name, category}], in taxonomy order. */
    function extract(value) {
        const text = toText(value);
        if (!text.trim()) return [];
        const found = [];
        for (const { skill, rx } of MATCHERS) {
            if (rx.some(r => r.test(text))) found.push({ name: skill.name, category: skill.cat });
        }
        return found;
    }

    /** Canonical skill for a name or alias ("k8s" -> Kubernetes), or null. */
    function canonical(name) {
        return BY_KEY.get(String(name || '').trim().toLowerCase()) || null;
    }

    /**
     * Full two-sided comparison. Inputs are arrays of {name} or strings.
     * score = matched / job skills (null when either side is empty).
     */
    function compare(jobSkills, resumeSkills) {
        const norm = list => {
            const out = new Map();
            (list || []).forEach(item => {
                const raw = typeof item === 'string' ? item : item?.name;
                const skill = canonical(raw);
                const name = skill ? skill.name : String(raw || '').trim();
                if (name && !out.has(name.toLowerCase())) out.set(name.toLowerCase(), { name, category: skill ? skill.cat : (item?.category || 'Other') });
            });
            return out;
        };
        const job = norm(jobSkills);
        const resume = norm(resumeSkills);
        const matched = [...job.values()].filter(s => resume.has(s.name.toLowerCase()));
        const missing = [...job.values()].filter(s => !resume.has(s.name.toLowerCase()));
        const extra = [...resume.values()].filter(s => !job.has(s.name.toLowerCase()));
        return {
            matched, missing, extra,
            jobTotal: job.size, resumeTotal: resume.size,
            score: job.size && resume.size ? Math.round(matched.length / job.size * 100) : null,
        };
    }

    window.CariaraSkills = { TAXONOMY, extract, compare, canonical, toText };
})();
