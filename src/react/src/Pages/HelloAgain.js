import React from "react";
import {Grid, GridColumn, Header, Image, Message} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {createFragmentContainer} from "react-relay"
import {graphql} from "graphql";

class HelloAgain extends React.Component {
    render() {
        {console.log(this.props)}
        return (
            <Grid textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                <GridColumn style={{maxWidth: 450}}>
                    <Header as='h2' color='teal' textAlign='center'>
                        <Image src='/logo.png'/> Hello!
                    </Header>
                    <Message>
                        Just a different route. Hello {this.props.user.username}!
                    </Message>
                    Back to the other route? <Link to='/bilby/' activeClassName="selected" exact {...this.props}>I
                    guess</Link>
                </GridColumn>
            </Grid>
        )
    }
}

// export default HelloAgain;
export default createFragmentContainer(HelloAgain, {
    user: graphql`
        fragment HelloAgain_user on UserDetails {
            username
        }
    `
});
