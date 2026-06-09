// Package orchestration is the gRPC client cosign-api uses to drive the worker.
package orchestration

import (
	"context"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/tensor-bloom/cosign/services/cosign-api/internal/pb"
)

type Client struct {
	conn *grpc.ClientConn
	c    pb.OrchestrationServiceClient
}

func Dial(addr string) (*Client, error) {
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}
	return &Client{conn: conn, c: pb.NewOrchestrationServiceClient(conn)}, nil
}

func (c *Client) SubmitGoal(ctx context.Context, goalUUID string) error {
	_, err := c.c.SubmitGoal(ctx, &pb.SubmitGoalRequest{GoalUuid: goalUUID})
	return err
}

func (c *Client) ResumeFromInterrupt(ctx context.Context, goalUUID, decision, feedback, editedJSON string) error {
	_, err := c.c.ResumeFromInterrupt(ctx, &pb.ResumeFromInterruptRequest{
		GoalUuid:          goalUUID,
		Decision:          decision,
		Feedback:          feedback,
		EditedPayloadJson: editedJSON,
	})
	return err
}

func (c *Client) CancelGoal(ctx context.Context, goalUUID string) error {
	_, err := c.c.CancelGoal(ctx, &pb.CancelGoalRequest{GoalUuid: goalUUID})
	return err
}

func (c *Client) Close() error { return c.conn.Close() }
