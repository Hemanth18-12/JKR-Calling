import type {
  IHookFunctions,
  IWebhookFunctions,
  INodeType,
  INodeTypeDescription,
  IWebhookResponseData,
} from "n8n-workflow";

export class JkrCallingTrigger implements INodeType {
  description: INodeTypeDescription = {
    displayName: "JKR Calling Trigger",
    name: "jkrCallingTrigger",
    icon: "file:jkr.svg",
    group: ["trigger"],
    version: 1,
    description: "Triggers on call completion, appointment bookings, or widget sessions from JKR Calling",
    defaults: {
      name: "JKR Calling Trigger",
    },
    inputs: [],
    outputs: ["main"],
    credentials: [
      {
        name: "jkrApi",
        required: true,
      },
    ],
    webhooks: [
      {
        name: "default",
        httpMethod: "POST",
        responseMode: "onReceived",
        path: "webhook",
      },
    ],
    properties: [
      {
        displayName: "Events",
        name: "events",
        type: "multiOptions",
        options: [
          { name: "Call Completed", value: "call.completed" },
          { name: "Appointment Booked", value: "appointment.booked" },
          { name: "Turn Completed", value: "call.turn_completed" },
          { name: "Widget Session Ended", value: "widget.session_ended" },
        ],
        default: ["call.completed", "appointment.booked"],
        required: true,
        description: "The events that will trigger this node",
      },
    ],
  };

  webhookMethods = {
    default: {
      async checkExists(this: IHookFunctions): Promise<boolean> {
        return false;
      },
      async create(this: IHookFunctions): Promise<boolean> {
        const webhookUrl = this.getNodeWebhookUrl("default");
        const credentials = await this.getCredentials("jkrApi");
        const baseUrl = (credentials.baseUrl as string).replace(/\/$/, "");
        const apiKey = credentials.apiKey as string;
        const events = this.getNodeParameter("events", []) as string[];

        await this.helpers.request({
          method: "POST",
          url: `${baseUrl}/api/v1/integrations/webhooks`,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${apiKey}`,
          },
          body: {
            url: webhookUrl,
            event_types: events,
          },
          json: true,
        });

        return true;
      },
      async delete(this: IHookFunctions): Promise<boolean> {
        return true;
      },
    },
  };

  async webhook(this: IWebhookFunctions): Promise<IWebhookResponseData> {
    const req = this.getRequestObject();
    return {
      workflowData: [this.helpers.returnJsonArray(req.body)],
    };
  }
}
