import type { GoogleCredential, GoogleIdentity } from '../auth/google.ts'

/**
 * Stand-in for Google Identity Services: renderButton draws a plain button that hands the
 * configured callback a fixed credential, as a person clicking Google's button would.
 */
export class FakeGoogleIdentity implements GoogleIdentity {
  static credential = 'fake-google-credential'
  clientIds: string[] = []
  private callback: ((response: GoogleCredential) => void) | null = null

  initialize(config: { client_id: string; callback: (response: GoogleCredential) => void }) {
    this.clientIds.push(config.client_id)
    this.callback = config.callback
  }

  renderButton(parent: HTMLElement, options: { text: string }) {
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = options.text === 'continue_with' ? 'Continue with Google' : 'Sign in with Google'
    button.addEventListener('click', () => {
      if (this.callback === null) throw new Error('renderButton before initialize')
      this.callback({ credential: FakeGoogleIdentity.credential })
    })
    parent.replaceChildren(button)
  }

  /** Installs itself as window.google so loadGoogleIdentity never fetches the script. */
  static install(): FakeGoogleIdentity {
    const fake = new FakeGoogleIdentity()
    window.google = { accounts: { id: fake } }
    return fake
  }
}
