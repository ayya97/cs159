import argparse
import math
import gym
import numpy as np
from itertools import count
from collections import namedtuple

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.distributions import Categorical
from torch.autograd import Variable
from torch.distributions.normal import Normal


parser = argparse.ArgumentParser(description='PyTorch actor-critic example')
parser.add_argument('--gamma', type=float, default=0.99, metavar='G',
                    help='discount factor (default: 0.99)')
parser.add_argument('--seed', type=int, default=543, metavar='N',
                    help='random seed (default: 1)')
parser.add_argument('--render', action='store_true',
                    help='render the environment')
parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                    help='interval between training status logs (default: 10)')
parser.add_argument('--entropy-coef', type=float, default=0.01)
args = parser.parse_args()


env = gym.make('InvertedPendulum-v2')
Max_action = env.action_space.high
Min_action = env.action_space.low
env.seed(args.seed)
torch.manual_seed(args.seed)


SavedAction = namedtuple('SavedAction', ['log_prob', 'value'])


class Policy(nn.Module):
    def __init__(self):
        super(Policy, self).__init__()
        self.affine1 = nn.Linear(4, 128)
        # 2 outputs because 2D space
        self.mu_head = nn.Linear(128, 1)
        self.sigma2_head = nn.Linear(128, 1)
        self.value_head = nn.Linear(128, 1)

        self.saved_actions = []
        self.rewards = []

    def forward(self, x):
        x = F.relu(self.affine1(x))
        return self.mu_head(x), F.softplus(self.sigma2_head(x)), self.value_head(x)
        # torch.exp(self.sigma2_head(x))

    def logprobs_and_entropy(self, x, actions):
        action_mean, sigma, _ = self(x)
        if sigma == torch.tensor(0.):
            sigma = torch.tensor(.0001)
        elif sigma != sigma:
            sigma = torch.tensor(.5001)

        action_std = torch.log(torch.sqrt(sigma)).exp()

        action_log_probs = -0.5 * ((actions - action_mean) / action_std).pow(2) - 0.5 * math.log(2 * math.pi) - math.log(torch.sqrt(sigma))

        action_log_probs = action_log_probs.sum(1)
        dist_entropy = 0.5 + math.log(2 * math.pi) + action_log_probs
        dist_entropy = dist_entropy.sum(-1).mean()

        return action_log_probs, dist_entropy


model = Policy()
optimizer = optim.Adam(model.parameters(), lr=3e-2)
eps = np.finfo(np.float32).eps.item()


def select_action(state):
    state = torch.from_numpy(state).float()
    # retrain the model
    mu, sigma, state_value = model(state)
    # creates a multivariate distribution
    if sigma != sigma:
    	sigma = torch.tensor(float(.5001))
    elif sigma == torch.tensor(0.):
        sigma = torch.tensor(.0001)
    m = Normal(mu, sigma)
    # samples an action according to the policy distribution
    action = m.sample()
    # print('mu: {0}, sigma: {1}'.format(mu, sigma))
    # print('log prob {0}'.format(m.log_prob(action)))
    model.saved_actions.append(SavedAction(m.log_prob(action), state_value))
    # returns the action as a number converted to python type and bounded within -1, 1
    #return max(Max_action, min(Min_action, m.sample().item()))
    #print('select_action(state)')
    #print( m.sample())
    #if  m.sample().item() > Max_action or m.sample().item() < Min_action:
    #    print('## \n ugh \n ##')
    return action.item()


def finish_episode(state):
    R = 0
    saved_actions = model.saved_actions
    policy_losses = []
    value_losses = []
    rewards = []
    # compute the reward for each state in the end of a rollout
    # action_log_probs, dist_entropy = model.logprobs_and_entropy(torch.from_numpy(state).float(),
            # torch.Tensor(saved_actions))
    for r in model.rewards[::-1]:
        R = r + args.gamma * R
        rewards.insert(0, R)
    rewards = torch.tensor(rewards)
    if rewards.std() != rewards.std():
        rewards = (rewards - rewards.mean()) / (eps)
    else:
        rewards = (rewards - rewards.mean()) / (rewards.std() + eps)

    for (log_prob, value), r in zip(saved_actions, rewards):
        # reward is the delta param
        # value += Variable(torch.randn(value.size()))
        reward = r - value.item()
        # theta
        # need gradient descent - so negative
        policy_losses.append(-log_prob * reward)
        # https://pytorch.org/docs/master/nn.html#torch.nn.SmoothL1Loss
        # feeds a weird difference between value and the reward
        value_losses.append(F.smooth_l1_loss(value, torch.tensor([r])))
    optimizer.zero_grad()
    # sum of 2 losses?
    loss = torch.stack(policy_losses).sum() + torch.stack(value_losses).sum()
            # + dist_entropy * args.entropy_coef
    # compute gradients
    loss.backward()
    # train the NN
    optimizer.step()
    del model.rewards[:]
    del model.saved_actions[:]


def main():
    running_reward = 10
    for i_episode in count(1):
        # random initialization
        state = env.reset()
        #print(state)
        for t in range(10000):  # Don't infinite loop while learning
            action = select_action(state)
            state, reward, done, _ = env.step(action)
            if args.render:
                env.render()
            model.rewards.append(reward)
            if done:
                break

        running_reward = running_reward * 0.99 + t * 0.01
        finish_episode(state)
        if i_episode % args.log_interval == 0:
            print('Episode {}\tLast length: {:5d}\tAverage length: {:.2f}'.format(
                i_episode, t, running_reward))
        if running_reward > env.spec.reward_threshold:
            print("Solved! Running reward is now {} and "
                  "the last episode runs to {} time steps!".format(running_reward, t))
            break


if __name__ == '__main__':
    main()
