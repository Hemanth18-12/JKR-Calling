import type {
  IExecuteFunctions,
  INodeExecutionData,
  INodeType,
  INodeTypeDescription,
  IDataObject,
} from "n8n-workflow";

export class JkrCalling implements INodeType {
  description: INodeTypeDescription = {
    displayName: "JKR Calling",
    name: "jkrCalling",
    icon: "file:jkr.svg",
    group: ["transform"],
    version: 1,
    description: "Automate AI voice calling, query transcripts, and monitor coin balances with JKR Calling",
    defaults: {
      name: "JKR Calling",
    },
    inputs: ["main"],
    outputs: ["main"],
    credentials: [
      {
        name: "jkrApi",
        required: true,
      },
    ],
    properties: [
      {
        displayName: "Resource",
        name: "resource",
        type: "options",
        noDataExpression: true,
        options: [
          { name: "Call", value: "call" },
          { name: "Agent", value: "agent" },
          { name: "Wallet", value: "wallet" },
        ],
        default: "call",
      },
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        displayOptions: {
          show: { resource: ["call"] },
        },
        options: [
          { name: "Dispatch Call", value: "dispatchCall", description: "Trigger an outbound AI call" },
          { name: "Get Transcript", value: "getTranscript", description: "Fetch call transcript" },
        ],
        default: "dispatchCall",
      },
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        displayOptions: {
          show: { resource: ["agent"] },
        },
        options: [
          { name: "List Agents", value: "listAgents", description: "List all configured voice agents" },
        ],
        default: "listAgents",
      },
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        displayOptions: {
          show: { resource: ["wallet"] },
        },
        options: [
          { name: "Check Balance", value: "checkBalance", description: "Get current coin balance" },
        ],
        default: "checkBalance",
      },
      // Call: Dispatch fields
      {
        displayName: "Agent ID",
        name: "agentId",
        type: "string",
        required: true,
        displayOptions: {
          show: { resource: ["call"], operation: ["dispatchCall"] },
        },
        default: "",
        description: "UUID of the AI agent to place the call",
      },
      {
        displayName: "Phone Number",
        name: "phoneNumber",
        type: "string",
        required: true,
        displayOptions: {
          show: { resource: ["call"], operation: ["dispatchCall"] },
        },
        default: "",
        placeholder: "+919876543210",
        description: "Customer recipient phone number in E.164 format",
      },
      {
        displayName: "Customer Name",
        name: "customerName",
        type: "string",
        displayOptions: {
          show: { resource: ["call"], operation: ["dispatchCall"] },
        },
        default: "Customer",
        description: "Name of the customer recipient",
      },
      // Call: Get Transcript fields
      {
        displayName: "Session ID",
        name: "sessionId",
        type: "string",
        required: true,
        displayOptions: {
          show: { resource: ["call"], operation: ["getTranscript"] },
        },
        default: "",
        description: "UUID of the call session",
      },
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const returnData: INodeExecutionData[] = [];
    const credentials = await this.getCredentials("jkrApi");
    const baseUrl = (credentials.baseUrl as string).replace(/\/$/, "");
    const apiKey = credentials.apiKey as string;

    const resource = this.getNodeParameter("resource", 0) as string;
    const operation = this.getNodeParameter("operation", 0) as string;

    for (let i = 0; i < items.length; i++) {
      try {
        let endpoint = "";
        let method = "GET";
        let body: IDataObject | undefined;

        if (resource === "call") {
          if (operation === "dispatchCall") {
            endpoint = "/api/v1/calls/dispatch";
            method = "POST";
            body = {
              agent_id: this.getNodeParameter("agentId", i) as string,
              to_phone_e164: this.getNodeParameter("phoneNumber", i) as string,
              metadata: {
                customer_name: this.getNodeParameter("customerName", i, "Customer") as string,
                source: "n8n_workflow",
              },
            };
          } else if (operation === "getTranscript") {
            const sessionId = this.getNodeParameter("sessionId", i) as string;
            endpoint = `/api/v1/calls/${sessionId}/transcript`;
            method = "GET";
          }
        } else if (resource === "agent") {
          endpoint = "/api/v1/agents";
          method = "GET";
        } else if (resource === "wallet") {
          endpoint = "/api/v1/coins/wallet";
          method = "GET";
        }

        const options: IDataObject = {
          method,
          url: `${baseUrl}${endpoint}`,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${apiKey}`,
          },
          json: true,
        };

        if (body) {
          options.body = body;
        }

        const responseData = await this.helpers.request(options as any);
        returnData.push({ json: responseData });
      } catch (error) {
        if (this.continueOnFail()) {
          returnData.push({ json: { error: (error as Error).message } });
          continue;
        }
        throw error;
      }
    }

    return [returnData];
  }
}
