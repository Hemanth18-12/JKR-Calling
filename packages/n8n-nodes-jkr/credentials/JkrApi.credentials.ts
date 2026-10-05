import type {
  ICredentialType,
  INodeProperties,
} from "n8n-workflow";

export class JkrApi implements ICredentialType {
  name = "jkrApi";
  displayName = "JKR Calling API";
  documentationUrl = "https://jkrcalling.com/docs/api";
  properties: INodeProperties[] = [
    {
      displayName: "API Key",
      name: "apiKey",
      type: "string",
      typeOptions: { password: true },
      default: "",
      required: true,
      description: "Your JKR Calling API key",
    },
    {
      displayName: "API Base URL",
      name: "baseUrl",
      type: "string",
      default: "https://jkr-calling-api.onrender.com",
      required: true,
      description: "Backend URL of the JKR Calling API instance",
    },
  ];
}
