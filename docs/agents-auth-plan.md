# Sign-in across the two agents

The design for per-user sign-in and data isolation, tracked in
[#1](https://github.com/erancha/home-finance-agent/issues/1) and mirrored in
[amex-agent#4](https://github.com/erancha/amex-agent/issues/4). Nothing here is built yet. Today
both web pages are open, all data belongs to one household, and the only credential is the shared
secret the home finance agent sends on every A2A call (`AMEX_AGENT_TOKEN`, amex-agent's
`APP_A2A_TOKEN`; see [a2a-contract.md](a2a-contract.md)).

In the diagram, tinted shapes and solid arrows run today; white shapes and dashed arrows are the
design. Colors mark who owns a component and who sends an arrow: blue for the home finance agent,
green for amex-agent, amber for Google, grey for the person at the browser.

```mermaid
flowchart TB
  U([Household member<br/>browser])

  subgraph HFA[Home finance agent  - Python]
    direction TB
    HP[Review page<br/>:8010]
    HAPI[FastAPI<br/>REST + live events]
    HG[LangGraph review]
    HLLM[Report writer<br/>LLM narrates totals]
    HDB[(Postgres<br/>reviews, checkpoints,<br/>merchant memory ⁶)]
    HSEC[/caller secret<br/>for amex-agent ³/]
  end

  subgraph AMX[amex-agent  - Java, third party ⁷]
    direction TB
    AP[Statements page<br/>:8020]
    AA2A[A2A server]
    AFS[/Statements<br/>one folder per user ⁶/]
    AREG[/allowed_callers ⁴<br/>shared_secret + client_id/]
  end

  subgraph GOOG[Google  - identity only ¹]
    GC1[OAuth client<br/>project: home finance]
    GC2[OAuth client<br/>project: amex-agent]
    GK[public keys ²]
  end

  %% user edges: 0-3
  U --> HP
  U --> AP
  U -. "Sign in with Google" .-> GC1
  U -. "Sign in with Google" .-> GC2

  %% home finance agent edges: 4-11
  HP --> HAPI
  HAPI --> HG
  HG --> HLLM
  HAPI --> HDB
  HG --> HDB
  HSEC -.-> HG
  HG -->|A2A stream| AA2A
  HG -. "user's ID token<br/>+ caller secret ³" .-> AA2A

  %% amex-agent edges: 12-16
  AP --> AFS
  AA2A --> AFS
  AA2A -. "secret selects entry,<br/>token audience = entry client_id" .-> AREG
  AA2A -.->|input-required<br/>missing statement| HP
  AA2A -.->|auth-required ⁵<br/>bad or expired token| HG

  %% google edges: 17-21
  GC1 -. "ID token" .-> HP
  GC2 -. "ID token" .-> AP
  GC1 -. "client_id, registered once ⁴" .-> AREG
  GK -. "verify every token ²" .-> HFA
  GK -. "verify every token ²" .-> AMX

  subgraph NOTES[Tinted and solid: runs today. White and dashed: the sign-in design, home-finance-agent#1]
    direction TB
    subgraph N1[¹ Google is the only identity. Each agent has its own OAuth client in its own Google Cloud project; a person signs in to each page with the same Google account, whose id is the user id in both agents.]
      n1[ ]
    end
    subgraph N2[² Every token is verified locally with the public keys Google publishes: signature, issuer, expiry and audience. A page accepts only its own client id as audience.]
      n2[ ]
    end
    subgraph N3[³ An A2A call carries two things: the shared secret proves the request comes from the home finance agent; the user's ID token, forwarded as received, says which user it is for.]
      n3[ ]
    end
    subgraph N4[⁴ amex-agent registers callers in one config list. The secret on the request selects the entry; the forwarded token's audience must equal that entry's client id. The operator edits entries by hand.]
      n4[ ]
    end
    subgraph N5[⁵ A missing, bad or expired token answers with the A2A auth-required state; the home finance agent asks the person to sign in again instead of failing the review.]
      n5[ ]
    end
    subgraph N6[⁶ Data is per user: a user column on every home-finance-agent table, a folder per user in amex-agent, and a person subscribes only to their own review stream.]
      n6[ ]
    end
    subgraph N7[⁷ Simplification: amex-agent honors a Google token issued to a partner's app. A separately operated amex-agent would rather issue its own tokens after verifying the user: OAuth 2.0 token exchange.]
      n7[ ]
    end
    n1 ~~~ n2 ~~~ n3 ~~~ n4 ~~~ n5 ~~~ n6 ~~~ n7
  end
  AFS ~~~ n1

  %% node colors per agent
  classDef user fill:#f3f4f6,stroke:#4b5563,color:#111827
  classDef hfa fill:#dbeafe,stroke:#1d4ed8,color:#111827
  classDef amx fill:#dcfce7,stroke:#15803d,color:#111827
  classDef goog fill:#fef3c7,stroke:#b45309,color:#111827
  classDef planned fill:#ffffff,stroke-dasharray: 5 5
  classDef blank fill:#ffffff,stroke:#ffffff,color:#ffffff
  class U user
  class HP,HAPI,HG,HLLM,HDB,HSEC hfa
  class AP,AA2A,AFS,AREG amx
  class GC1,GC2,GK goog
  class GC1,GC2,GK,AREG,HSEC planned
  class n1,n2,n3,n4,n5,n6,n7 blank
  style HFA fill:#eff6ff,stroke:#1d4ed8
  style AMX fill:#f0fdf4,stroke:#15803d
  style GOOG fill:#ffffff,stroke:#b45309,stroke-dasharray: 5 5
  style NOTES fill:#ffffff,stroke:#ffffff

  %% arrow colors by originating agent
  linkStyle 0,1,2,3 stroke:#4b5563
  linkStyle 4,5,6,7,8,9,10,11 stroke:#1d4ed8
  linkStyle 12,13,14,15,16 stroke:#15803d
  linkStyle 17,18,19,20,21 stroke:#b45309
  style N1 fill:#ffffff,stroke:#ffffff
  style N2 fill:#ffffff,stroke:#ffffff
  style N3 fill:#ffffff,stroke:#ffffff
  style N4 fill:#ffffff,stroke:#ffffff
  style N5 fill:#ffffff,stroke:#ffffff
  style N6 fill:#ffffff,stroke:#ffffff
  style N7 fill:#ffffff,stroke:#ffffff
```

## The design in six points

**Google is the only identity.** Each agent will have its own OAuth client in its own Google Cloud
project, so the two share nothing by default; two projects under one Google account stand in for
two operators. A person will sign in to each page with the same Google account and nothing else.
The stable Google account id will be the user id in both agents. No registration step, no stored
passwords.

**Every token is verified locally, the same way everywhere.** Both agents will cache the public
keys Google publishes and check each token's signature, issuer, expiry and audience. The audience
names the client the token was issued to; a page will accept only its own client id.

**An A2A call will carry two things.** The shared secret, which stays as it is today, will prove
the request comes from the home finance agent. The signed-in person's Google ID token, forwarded
as received, will say which user the call is for, and amex-agent will verify it itself rather than
trust a bare user id.

**amex-agent will register callers in config, not in a database.** One entry per caller:

```yaml
allowed_callers:
  - name: home-finance-agent
    shared_secret: <random>
    client_id: <the home finance agent's Google client id>
```

The secret on a request selects the entry, compared in constant time; the forwarded token's
audience must equal that entry's client id. Registration is the amex-agent operator adding an
entry, and removing it revokes the caller. Only the secret is confidential; the client id is
public. For the demo, `init-env.sh` will write the single entry the way it syncs the token today.
The agent card will advertise the scheme.

**A missing, bad or expired token** will be answered with the A2A auth-required task state. The
home finance agent will treat it as one more stream state and ask the person to sign in again,
rather than failing the review.

**Data will be keyed by user.** In the home finance agent: reviews, review events, checkpoints,
merchant memory, and the live event stream, where a person may subscribe only to their own review.
In amex-agent: a statements folder per Google id, a statements page that lists only the signed-in
person's files, and a missing-statement link that lands the same person there.

## The stated simplification

amex-agent will honor a Google token that was issued to a partner's app. That is what two services
trusting the same identity provider do under one roof. A genuinely separate operator would more
likely issue its own access tokens after verifying the person, through OAuth 2.0 token exchange
(RFC 8693), and would advertise an OAuth 2.0 scheme of its own in the agent card. Everything else
above would stay as it is.
