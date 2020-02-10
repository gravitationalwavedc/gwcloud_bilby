import React from "react";
import {Grid, Header, Image, Message} from "semantic-ui-react";
import Link from 'found/lib/Link';

class Hello extends React.Component {
    constructor() {
        super();
    }

    render() {
        return (
            <Grid textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                <Grid.Column style={{maxWidth: 450}}>
                    <Header as='h2' color='teal' textAlign='center'>
                        <Image src='/logo.png'/> Hello!
                    </Header>
                    <Message>
                        Hello {this.props.gwclouduser ? this.props.gwclouduser.username : ""}!
                    </Message>
                    Go to another route? <Link to='/bilby/another/' activeClassName="selected"
                                               exact {...this.props}>Yes!</Link>
                </Grid.Column>
            </Grid>
        )
    }
}

export default Hello;