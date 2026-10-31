"use strict";
// Tokens stay in memory. Only a short-lived PKCE transaction uses sessionStorage.
window.vdsAuth = (() => {
  let config = null, accessToken = null, expiresAt = 0;
  const authPanel = document.querySelector("#auth-panel");
  const signIn = document.querySelector("#sign-in");
  const signOut = document.querySelector("#sign-out");
  const message = document.querySelector("#auth-message");
  const layout = document.querySelector(".layout");
  const transactionKey = "vds_pkce";
  const encoded = (bytes) => btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
  const random = () => encoded(crypto.getRandomValues(new Uint8Array(32)));
  const digest = async (text) => new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
  function gate(text = "Sign in to open your private development workspace.") {
    accessToken = null; expiresAt = 0;
    layout.hidden = true; layout.inert = true;
    authPanel.hidden = false; signOut.hidden = true; message.textContent = text;
  }
  async function login() {
    signIn.disabled = true;
    try {
      const verifier = random(), state = random();
      sessionStorage.setItem(transactionKey, JSON.stringify({verifier, state, created: Date.now()}));
      const params = new URLSearchParams({response_type:"code", client_id:config.client_id,
        redirect_uri:location.origin + "/", scope:"openid profile", state,
        code_challenge_method:"S256", code_challenge:encoded(await digest(verifier))});
      location.assign(config.domain + "/oauth2/authorize?" + params);
    } catch {gate("Sign-in could not start. Try again."); signIn.disabled = false;}
  }
  const ready = (async () => {
    // Only the hosted build supplies this public configuration; local checks keep
    // their existing loopback identity and do not contact an identity provider.
    if (!["localhost", "127.0.0.1", "[::1]"].includes(location.hostname)) {
      gate("Connecting to secure sign-in…"); signIn.disabled = true;
      const response = await fetch("/config.json", {cache:"no-store"});
      if (!response.ok) throw new Error("Hosted workspace configuration is unavailable.");
      config = await response.json();
      if (!/^https:\/\/[a-z0-9-]+\.auth\.[a-z0-9-]+\.amazoncognito\.com$/.test(config.domain) || !/^[a-z0-9]+$/.test(config.client_id)) {
        throw new Error("Hosted sign-in configuration is invalid.");
      }
      document.querySelector("#studio-link").hidden = true;
      signIn.disabled = false;
      signIn.addEventListener("click", login);
      signOut.addEventListener("click", () => {
        gate(); localStorage.removeItem("vds_dataset"); sessionStorage.removeItem(transactionKey);
        location.assign(config.domain + "/logout?" + new URLSearchParams({client_id:config.client_id, logout_uri:location.origin + "/"}));
      });
      const params = new URLSearchParams(location.search);
      const code = params.get("code"), oauthError = params.get("error");
      if (code || oauthError) {
        const saved = sessionStorage.getItem(transactionKey);
        sessionStorage.removeItem(transactionKey);
        history.replaceState(null, "", "/");
        try {
          const transaction = JSON.parse(saved || "null");
          if (oauthError || !transaction || params.get("state") !== transaction.state || Date.now() - transaction.created > 600000) {
            throw new Error("The sign-in request expired. Please start again.");
          }
          const response = await fetch(config.domain + "/oauth2/token", {method:"POST",
            headers:{"Content-Type":"application/x-www-form-urlencoded"},
            body:new URLSearchParams({grant_type:"authorization_code", client_id:config.client_id,
              redirect_uri:location.origin + "/", code_verifier:transaction.verifier, code})});
          if (!response.ok) throw new Error("Sign-in could not finish. Please try again.");
          const tokens = await response.json();
          if (!tokens.access_token || !(tokens.expires_in > 0)) throw new Error("Sign-in did not return access.");
          accessToken = tokens.access_token; expiresAt = Date.now() + tokens.expires_in * 1000;
          localStorage.removeItem("vds_dataset");
          authPanel.hidden = true; layout.hidden = false; layout.inert = false; signOut.hidden = false;
          return true;
        } catch (error) {gate(error.message); return false;}
      }
      gate(); return false;
    }
    return true;
  })().catch(error => {gate(error.message); throw error;});
  return {
    ready,
    hosted: () => !!config,
    async request(path, body) {
      await ready;
      const headers = {};
      if (config) {
        if (!accessToken || Date.now() >= expiresAt - 10000) {
          gate("Your sign-in expired. Sign in again to continue.");
          throw new Error("Sign in to continue.");
        }
        headers["x-vds-token"] = accessToken;
      }
      const options = {headers, cache:"no-store"};
      if (body !== undefined) {
        options.method = "POST"; options.body = JSON.stringify(body);
        headers["Content-Type"] = "application/json";
        if (config) headers["x-amz-content-sha256"] = [...await digest(options.body)].map(b => b.toString(16).padStart(2, "0")).join("");
      }
      const response = await fetch(`/api/v2/${path}`, options);
      if (config && response.status === 401) gate("Your sign-in is invalid. Sign in again.");
      return response;
    }
  };
})();
