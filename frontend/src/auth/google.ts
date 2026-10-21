/**
 * Google Identity Services, the script behind the Sign in with Google button. It is loaded from
 * Google once per page; tests install a stand-in on window.google before anything asks for it.
 */
const SCRIPT_URL = 'https://accounts.google.com/gsi/client'

export interface GoogleCredential {
  /** The ID token, a signed statement of who signed in, issued to our client id. */
  credential: string
}

export interface GoogleIdentity {
  initialize(config: { client_id: string; callback: (response: GoogleCredential) => void }): void
  renderButton(parent: HTMLElement, options: { theme: 'outline'; size: 'large'; text: string }): void
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleIdentity } }
  }
}

let loading: Promise<GoogleIdentity> | null = null

export function loadGoogleIdentity(): Promise<GoogleIdentity> {
  if (window.google !== undefined) return Promise.resolve(window.google.accounts.id)
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_URL
    script.async = true
    script.onload = () => {
      if (window.google === undefined) {
        reject(new Error('the Google sign-in script loaded without defining window.google'))
        return
      }
      resolve(window.google.accounts.id)
    }
    script.onerror = () => {
      loading = null
      reject(new Error('the Google sign-in script could not be loaded'))
    }
    document.head.append(script)
  })
  return loading
}
