import React from "react";
import {Grid, Header, Image, Message} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";
import {graphql} from "graphql";

class Hello extends React.Component {
    constructor() {
        super();

        this.state = {
            message: "No response yet"
        };

        commitMutation(harnessApi.getEnvironment("test"), {
            mutation: graphql`mutation HelloAgainMutation($input: HelloInput!)
                {
                  hello(input: $input) 
                  {
                    result
                  }
                }`,
            variables: {
                input: {
                    message: "Message to the server!"
                }
            },
            onCompleted: (response, errors) => {
                this.setState({
                    ...this.state,
                    message: response.result
                })
            },
        });
    }

    render() {
        return (
            <Grid textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                <Grid.Column style={{maxWidth: 450}}>
                    <Header as='h2' color='teal' textAlign='center'>
                        <Image src='/logo.png'/> Hello!
                    </Header>
                    <Message>
                        Just a different route. Hello {this.props.username}!
                    </Message>
                    Back to the other route? <Link to='/test/' activeClassName="selected" exact {...this.props}>I
                    guess</Link>
                </Grid.Column>
            </Grid>
        )
    }
}

export default Hello;