import re
import time
import json
import types
import collections
import rich.console

from .utils import rgetattr, rsetattr, cache_decoder, print_status, Colors
from .constants import (
    X,
    CHECK,
    ARROW,
    DOT,
    CACHE_REF,
    ANIMATION_SLEEP,
    USER_CLIENT_MODULE_NAME,
)


class Deployment:
    def __init__(self, flags, config, clients):
        """Initialize the deployment."""
        self.cache = (nested_dict := lambda: collections.defaultdict(nested_dict))()
        self.flags = flags
        self.config = config
        self.clients = clients

    def resolve(self, args):
        """Resolve all cache references in the args dict."""
        return json.loads(json.dumps(args), cls=cache_decoder(self.cache))

    def find_recursive_actions(self, args):
        """Look through the args dict and find all actions for cache references."""
        return [
            action
            for cache_reference in re.findall(CACHE_REF, json.dumps(args))
            for action_prefixes in [
                # Generate all prefixes of the cache reference to find matching actions
                cache_reference.split(DOT)[: i + 1]
                for i in range(len(cache_reference.split(DOT)))
            ]
            if (action := DOT.join(action_prefixes)) in self.config
        ]

    def run(self, actions):
        """Run the deployment."""
        for action in actions:
            self.execute(action)

    # `action` is a str of form <one>.<or>.<more>.<namespaces>.<client>.<fn>
    def execute(self, action, seen=set()):
        """Execute an action."""
        # Split the action into its components
        *namespaces, client_name, fn_name = action.split(DOT)
        id = f"{DOT.join(namespaces)}.{client_name}.{fn_name}"

        # If we've already seen this action when recursing, return
        if id in seen:
            return
        else:
            seen.add(id)

        # Execute actions recursively
        for dep_action in self.find_recursive_actions(self.config[action]):
            self.execute(dep_action, seen)

        # Try to get the function from the client
        try:
            fn = rgetattr(
                self.clients,
                (
                    fn_name
                    if client_name == USER_CLIENT_MODULE_NAME
                    else f"{client_name}.{fn_name}"
                ),
            )
        except Exception:
            print_status(id, Colors.FAIL, X)
            raise

        # If we're dry running, print the args (unresolved)
        if self.flags.dry:
            print(f"{Colors.OKBLUE}{id}{Colors.ENDC}")
            print_status(self.config[action], Colors.OKBLUE, ARROW)
            return

        # Print the action
        with rich.console.Console().status(f"[bold grey]{id}"):
            time.sleep(ANIMATION_SLEEP)

            # Try to resolve the args
            try:
                args = self.resolve(self.config[action])
            except Exception:
                print_status(id, Colors.FAIL, X)
                print_status(self.config[action], Colors.FAIL, X)
                raise

            # If we're verbose, print the resolved args
            if self.flags.verbose and args:
                print_status(args, Colors.OKBLUE, ARROW)

            # Try to execute the function
            try:
                if isinstance(args, dict):
                    value = fn(**args)
                elif isinstance(args, list):
                    value = fn(*args)
                elif args:
                    value = fn(args)
                else:
                    value = fn()

                # Auto-unpack generator results
                if isinstance(value, types.GeneratorType):
                    value = list(value)
            except Exception:
                print_status(id, Colors.FAIL, X)
                print_status(self.config[action], Colors.FAIL, X)
                raise

            # If we're verbose, print the result
            if self.flags.verbose and value:
                print_status(value, Colors.OKGREEN, CHECK)

            # Try to cache the result
            try:
                rsetattr(self.cache, id, value)
            except Exception:
                print_status(id, Colors.FAIL, X)
                print_status(value, Colors.FAIL, X)
                raise

        print_status(id, Colors.OKGREEN, CHECK)
