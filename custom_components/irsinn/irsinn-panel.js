class IRsinnPanel extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <ha-card header="IRsinn Commands">
        <table>
          <tr><th>Key</th><th>Value (Base64)</th><th>Actions</th></tr>
        </table>
      </ha-card>
    `;
  }
}
customElements.define('irsinn-panel', IRsinnPanel);
