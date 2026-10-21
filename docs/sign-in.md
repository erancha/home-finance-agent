# Sign-in across the two agents

Both agents sign people in with Google and nothing else, and every piece of data belongs to the
person who signed in. The two agents trust each other through one explicit step: the home finance
agent is registered with the card agent as a caller. amex-agent, the demo's card agent, stands
for any card agent below. This page explains how that works and how to set up the Google side;
the message details are in [a2a-contract.md](a2a-contract.md), the code in
[architecture.md](architecture.md#sign-in).

**Contents:** [The design in six points](#the-design-in-six-points) ·
[Setting up Google](#setting-up-google) ·
[What a real card issuer would do differently](#what-a-real-card-issuer-would-do-differently)

In the diagram, colors mark who owns a component and who sends an arrow: blue for the home finance
agent, green for the card agent, amber for Google, grey for the person at the browser.

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
    HSEC[/caller secret<br/>for the card agent ³/]
  end

  subgraph AMX[Card agent  - another operator ⁷]
    direction TB
    AP[Statements page]
    AA2A[A2A server]
    AFS[/Statements<br/>per user ⁶/]
    AREG[/registered callers ⁴<br/>secret + client id/]
  end

  subgraph GOOG[Google  - identity only ¹]
    GC1[OAuth client<br/>project: home finance]
    GC2[OAuth client<br/>project: card agent]
    GK[public keys ²]
  end

  %% user edges: 0-3
  U --> HP
  U --> AP
  U -- "Sign in with Google" --> GC1
  U -- "Sign in with Google" --> GC2

  %% home finance agent edges: 4-11
  HP --> HAPI
  HAPI --> HG
  HG --> HLLM
  HAPI --> HDB
  HG --> HDB
  HSEC --> HG
  HG -->|A2A stream| AA2A
  HG -- "user's ID token<br/>+ caller secret ³" --> AA2A

  %% card agent edges: 12-16
  AP --> AFS
  AA2A --> AFS
  AA2A -- "secret selects entry,<br/>token audience = entry client_id" --> AREG
  AA2A -.->|input-required<br/>missing statement| HP
  AA2A -.->|auth-required ⁵<br/>bad or expired token| HG

  %% google edges: 17-21
  GC1 -- "ID token" --> HP
  GC2 -- "ID token" --> AP
  GC1 -- "client_id, registered once ⁴" --> AREG
  GK -- "verify every token ²" --> HFA
  GK -- "verify every token ²" --> AMX

  subgraph NOTES[ ]
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
    subgraph N4[⁴ The card agent registers callers in config of its own: a name, the secret it issued, the caller's client id. The secret on the request selects the entry; the forwarded token's audience must equal that entry's client id.]
      n4[ ]
    end
    subgraph N5[⁵ A missing, bad or expired token answers with the A2A auth-required state; the home finance agent asks the person to sign in again instead of failing the review.]
      n5[ ]
    end
    subgraph N6[⁶ Data is per user: a user column on every home-finance-agent table, the card agent's statements kept per user, and a person subscribes only to their own review stream.]
      n6[ ]
    end
    subgraph N7[⁷ Simplification: the card agent honors a Google token issued to a partner's app. A separately operated one would rather issue its own tokens after verifying the user: OAuth 2.0 token exchange.]
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
  classDef blank fill:#ffffff,stroke:#ffffff,color:#ffffff
  class U user
  class HP,HAPI,HG,HLLM,HDB,HSEC hfa
  class AP,AA2A,AFS,AREG amx
  class GC1,GC2,GK goog
  class n1,n2,n3,n4,n5,n6,n7 blank
  style HFA fill:#eff6ff,stroke:#1d4ed8
  style AMX fill:#f0fdf4,stroke:#15803d
  style GOOG fill:#fffbeb,stroke:#b45309
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

**Google is the only identity.** Each agent has its own OAuth client in its own Google Cloud
project, so the two share nothing by default; two projects under one Google account stand in for
two operators. A person signs in to each page with the same Google account and nothing else. The
stable Google account id is the user id in both agents. No registration step, no stored passwords.

**Every token is verified locally, the same way everywhere.** Both agents fetch and cache the
public keys Google publishes and check each token's signature, issuer, expiry and audience. The
audience names the client the token was issued to; a page accepts only its own client id. A
Google ID token lives about an hour; when it expires, the next request answers 401 and the page
shows the sign-in button again. There are no refresh tokens and no server-side sessions.

**An A2A call carries two things.** The shared secret, under the header `X-Caller-Secret`, proves
the request comes from the home finance agent. The signed-in person's Google ID token, forwarded
as received in `Authorization: Bearer`, says which person the call is for, and the card agent
verifies it itself rather than trust a bare user id.

**The card agent registers callers in config of its own, not in a database.** One entry per
caller: a name, the secret the card agent issued to it, and the Google client id of the caller's
own sign-in. The secret on a request selects the entry; the forwarded token's audience must equal
that entry's client id. Registration is the card agent's operator running its registration script,
which issues the secret; removing the entry revokes the caller. Only the secret is confidential;
the client id is public. The hand-over to this side, and `add-card-agent.sh` recording it, is in
[connecting-agents.md](connecting-agents.md). The agent card advertises both schemes.

**A missing, bad or expired token** is answered with the A2A auth-required task state. The home
finance agent treats it as one more pause: the review waits on a "sign in again and continue"
question, the page shows the Google button inline, and the continue forwards the fresh token.

**Data is keyed by user.** In the home finance agent: reviews, review events, checkpoints, merchant
memory, and the live event stream, where a person may subscribe only to their own review. The
card agent keeps its statements per user too, and a missing-statement link lands the same person
on its page.

## Setting up Google

Give each agent its own Google Cloud project with one OAuth client, rather than two clients in one
project. Both work technically: a client id is what an agent verifies, and two clients in one
project are as distinct as two in separate projects. Two projects is still the right choice,
because it is the shape of the real deployment, where the card agent belongs to another operator:
each project has its own consent screen, test users and owner, and nothing in one console touches
the other. One project would make the two agents look like one app, which is what this demo
exists to show they are not. The steps are this agent's; a card agent's own docs give its origin
and setting.

1. **Create the project.** In the [Google Cloud console](https://console.cloud.google.com/), open
   the project picker at the top of the page, choose **New project**, name it
   `home-finance-agent` and create it. Make sure the picker now shows that project:
   everything below is per project.
2. **Configure the consent screen.** Search the top bar for **Google Auth Platform** and open it
   (older consoles reach the same place as **APIs & Services → OAuth consent screen**). A new
   project shows "Google Auth Platform not configured yet" with a **Get started** button. The
   wizard asks for an app name (the agent's name) and your email as the support email, then the
   audience, where you choose **External**, then a contact email, then your agreement to Google's
   policy. **Create** finishes it. The app is now in **Testing**, which is where it stays: no
   verification, no publishing.
3. **Add the test users.** Open **Audience** and, under **Test users**, add the household's
   Google accounts. While an app is in testing, Google signs in nobody else, with an "access
   blocked" page. **Data Access** stays empty: the agent needs no scope beyond the defaults.
4. **Create the client.** Open **Clients → Create client**, choose **Web application**, give it a
   name, and under **Authorized JavaScript origins** add `http://localhost:8010`. Leave
   **Authorized redirect URIs**
   empty: the sign-in button hands the token to the page directly. **Create** shows the client id,
   a long string ending in `.apps.googleusercontent.com`, next to a client secret and a JSON
   download. Only the client id is needed; it stays listed on the Clients page. Ignore the secret
   and the download, close the dialog, and the "shown once" warning costs nothing: the agent
   verifies tokens, it never redeems codes, so nothing in this repo has a place for the secret.
5. **Give it to the agent.** Copy the client id into `GOOGLE_CLIENT_ID` in `backend/.env`, the
   file `init-env.sh` wrote.

Then `start.sh`; connecting a card agent is in [connecting-agents.md](connecting-agents.md).

Google accepts only `localhost` or a public hostname as an authorized origin, never a private
address such as `10.0.0.23`, so a phone on the same network cannot sign in until the stack is
reached through a hostname.

## What a real card issuer would do differently

The card agent accepts a Google token that was issued to the home finance agent's app. A real card
issuer would not: that token proves to the home finance agent who the person is, and says nothing
about whether the issuer knows them. The issuer would have the person sign in at its own site, issue
a token of its own, and let the home finance agent act for the person with that token.

The demo skips this because one household runs both agents. The caller secret and the client-id
check in the caller registry already decide who may call and for which app's users, which is the
guarantee that matters at this scale. Everything else in this document would stay as it is.
